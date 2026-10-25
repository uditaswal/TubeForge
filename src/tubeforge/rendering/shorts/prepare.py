"""Native speech preparation; heavy TTS and alignment run sequentially.

This module does not approve content. The application must bind and approve the
topic before calling it. The CLI also supports explicitly labelled test data.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
import hashlib
import json
import logging
import re
from pathlib import Path
import sys
import time

import numpy as np
import soundfile as sf

from tubeforge.core.config import load_settings
from tubeforge.core.errors import ProviderValidationError, RepairableAlignmentResult, RetryableProviderError
from tubeforge.domain.contracts import VoiceRequest
from tubeforge.pipeline.alignment import LocalWhisperDTWAligner, LocalWordAligner, alignment_model_sha256
from tubeforge.providers.voice.kokoro import KokoroVoiceProvider
from tubeforge.providers.voice.piper import PiperVoiceProvider
from .encode import checked, file_hash
from .schema import ShortsTopic
from .spoken import collapse_alignment, prepare_spoken, profile_hash
from .timeline import SceneTiming, Timeline, Word

LOG = logging.getLogger(__name__)


def compress_pauses(audio, sr, max_pause, threshold=.004, frame_seconds=.01):
    """Shorten every internal silence longer than ``max_pause`` to exactly that length."""
    frame = max(1, round(frame_seconds * sr))
    count = len(audio) // frame
    if count == 0:
        return audio
    quiet = np.abs(audio[:count * frame]).reshape(count, frame).max(axis=1) < threshold
    keep, limit, index = [], max(1, round(max_pause / frame_seconds)), 0
    while index < count:
        end = index
        while end < count and quiet[end] == quiet[index]:
            end += 1
        if quiet[index] and end - index > limit and index > 0 and end < count:
            half = limit // 2
            keep.append((index * frame, (index + half) * frame))
            keep.append(((end - (limit - half)) * frame, end * frame))
        else:
            keep.append((index * frame, end * frame))
        index = end
    keep.append((count * frame, len(audio)))
    return np.concatenate([audio[start:stop] for start, stop in keep])


def synthesize(topic, settings, output, voice):
    pacing = settings.pipeline.reference_short
    primary = KokoroVoiceProvider(settings.pipeline.kokoro.model_copy(update={"speed": pacing.voice_speed}))
    fallback = PiperVoiceProvider(settings.pipeline.piper)
    identity = profile_hash(profile=pacing.spoken_profile, lexicon=pacing.pronunciation_lexicon,
                            group_size=pacing.speech_group_size, voice_processing=pacing.voice_processing)
    groups = []
    for first in range(0, len(topic.scenes), pacing.speech_group_size):
        scenes = topic.scenes[first:first + pacing.speech_group_size]
        forms = [prepare_spoken(scene.vo, profile=pacing.spoken_profile,
                                lexicon=pacing.pronunciation_lexicon) for scene in scenes]
        spoken_text = " ".join(form.text for form in forms)
        request = VoiceRequest(text=spoken_text, language="en", voice_id=voice, section_id=scenes[0].scene_id,
                               settings=(("spoken_profile_sha256", identity),))
        warning = None
        try:
            result = primary.synthesize(request)
        except (ProviderValidationError, RetryableProviderError) as error:
            warning = f"Kokoro unavailable; local Piper fallback: {type(error).__name__}"
            LOG.warning(warning)
            result = fallback.synthesize(request.model_copy(update={"voice_id": settings.pipeline.piper.voice_id}))
        audio, sr = sf.read(result.artifact_path, dtype="float32")
        if audio.ndim != 1 or not np.isfinite(audio).all():
            raise ValueError("voice output must be finite mono samples")
        active = np.where(np.abs(audio) > .004)[0]
        if not len(active):
            raise ValueError("voice output is silent")
        audio = audio[max(0, active[0] - round(.04 * sr)):min(len(audio), active[-1] + round(.1 * sr))]
        audio = compress_pauses(audio, sr, pacing.max_pause_seconds)
        raw = output / f"voice-group-{first:02d}-raw.wav"
        sf.write(raw, audio, sr, subtype="PCM_16")
        path = raw
        if pacing.voice_processing == "gentle-v1":
            path = output / f"voice-group-{first:02d}.wav"
            checked([pacing.ffmpeg_executable, "-y", "-v", "error", "-i", str(raw), "-af",
                     "highpass=f=70,acompressor=threshold=0.1:ratio=1.6:attack=15:release=120:makeup=1",
                     "-ar", str(sr), "-ac", "1", "-c:a", "pcm_s16le", str(path)],
                    deadline=time.monotonic() + 90, cancelled=lambda: False)
        group_audio, group_sr = sf.read(path, dtype="float32")
        if group_sr != sr or group_audio.ndim != 1 or not np.isfinite(group_audio).all():
            raise ValueError("processed voice is not finite mono speech")
        groups.append({"first_scene": first, "scene_ids": [s.scene_id for s in scenes],
                       "spoken_text": spoken_text,
                       "spoken_sha256": hashlib.sha256(spoken_text.encode()).hexdigest(),
                       "alignment_text": " ".join(form.alignment_text for form in forms),
                       "display_spans": [form.display_spans for form in forms],
                       "applied": [form.applied for form in forms],
                       "file": path.name, "sha256": file_hash(path), "raw_file": raw.name,
                       "raw_sha256": file_hash(raw), "provider": result.provider_name,
                       "warning": warning, "duration": len(group_audio) / sr})
    (output / "voice-manifest.json").write_text(json.dumps({"version": "speech-prep-v1",
        "profile_sha256": identity, "topic_sha256": file_hash(output / "topic.json"),
        "groups": groups}, indent=2) + "\n")


def _upgrade_legacy_manifest(topic, records):
    """Express a pre-speech-prep per-scene manifest (a bare list) as one-scene groups.

    Jobs paused after voice generation before the grouped format landed must resume.
    Legacy audio was made with no spoken expansion, grouping or processing, so it maps
    to the default ("off") profile; a changed profile is still rejected by `align`.
    """
    if len(records) != len(topic.scenes):
        raise ValueError("voice manifest no longer matches scene audio")
    groups = []
    for index, (scene, record) in enumerate(zip(topic.scenes, records, strict=True)):
        if record.get("scene_id") != scene.scene_id:
            raise ValueError("voice manifest no longer matches scene audio")
        form = prepare_spoken(scene.vo, profile="off", lexicon={})
        groups.append({"first_scene": index, "scene_ids": [scene.scene_id], "spoken_text": form.text,
                       "spoken_sha256": hashlib.sha256(form.text.encode()).hexdigest(),
                       "alignment_text": form.alignment_text,
                       "display_spans": [[list(span) for span in form.display_spans]],
                       "applied": [[]], "file": record["file"], "sha256": record["sha256"],
                       "raw_file": record["file"], "raw_sha256": record["sha256"],
                       "provider": record.get("provider"), "warning": record.get("warning"),
                       "duration": record.get("duration")})
    return {"version": "speech-prep-v1", "legacy": True,
            "profile_sha256": profile_hash(profile="off", lexicon={}, group_size=1, voice_processing="off"),
            "topic_sha256": None, "groups": groups}


def align(topic, output, model_path, tail=.18, *, pacing=None):
    manifest = json.loads((output / "voice-manifest.json").read_text())
    if isinstance(manifest, list):
        manifest = _upgrade_legacy_manifest(topic, manifest)
    if manifest.get("version") != "speech-prep-v1" or (
            not manifest.get("legacy") and manifest.get("topic_sha256") != file_hash(output / "topic.json")):
        raise ValueError("voice manifest no longer matches reviewed topic")
    if pacing is not None and manifest.get("profile_sha256") != profile_hash(
            profile=pacing.spoken_profile, lexicon=pacing.pronunciation_lexicon,
            group_size=pacing.speech_group_size, voice_processing=pacing.voice_processing):
        raise ValueError("speech settings changed between synthesis and alignment")
    warning = None
    try:
        aligner = LocalWhisperDTWAligner(model_path=model_path, model_sha256=alignment_model_sha256(model_path))
    except (ProviderValidationError, OSError) as error:
        aligner = None
        warning = f"Forced alignment unavailable; estimated timing: {type(error).__name__}"
        LOG.warning(warning)
    timings, pieces, cursor, warnings = [], [], 0.0, []
    scene_index = 0
    for record in manifest["groups"]:
        scenes = topic.scenes[scene_index:scene_index + len(record["scene_ids"])]
        if [scene.scene_id for scene in scenes] != record["scene_ids"] or record["first_scene"] != scene_index:
            raise ValueError("voice group does not match reviewed scene order")
        forms = [prepare_spoken(scene.vo, profile=pacing.spoken_profile,
                                lexicon=pacing.pronunciation_lexicon) for scene in scenes] if pacing else None
        if forms and (record["spoken_text"] != " ".join(form.text for form in forms) or
                      record["alignment_text"] != " ".join(form.alignment_text for form in forms) or
                      record["display_spans"] != [list(map(list, form.display_spans)) for form in forms]):
            raise ValueError("voice group spoken/display mapping changed")
        if hashlib.sha256(record["spoken_text"].encode()).hexdigest() != record["spoken_sha256"]:
            raise ValueError("spoken text changed after synthesis")
        path = output / record["file"]
        if file_hash(path) != record["sha256"] or file_hash(output / record["raw_file"]) != record["raw_sha256"]:
            raise ValueError("voice group audio changed after synthesis")
        audio, sr = sf.read(path, dtype="float32")
        duration = len(audio) / sr
        kwargs = dict(audio_path=path, text=record["alignment_text"], phrase_id=scenes[0].scene_id,
                      section_id=scenes[0].scene_id, phrase_start_seconds=0,
                      phrase_end_seconds=duration, ordinal_start=0)
        method, scene_warning = "whisper-base-en-dtw-v1", warning
        try:
            if aligner is None:
                raise ProviderValidationError("forced alignment unavailable")
            try:
                try:
                    measured = aligner.align(**kwargs)
                except RetryableProviderError:
                    # Transient model/memory failure: one retry before the logged estimate fallback.
                    time.sleep(2)
                    measured = aligner.align(**kwargs)
            except RepairableAlignmentResult:
                measured = aligner.align(**kwargs, configuration="normalized-overlap-v1")
                method += ":normalized-overlap-v1"
        except (ProviderValidationError, RetryableProviderError) as error:
            measured = LocalWordAligner().align(**kwargs)
            method = "estimated-waveform-weighted-v1"
            scene_warning = f"Estimated timing requires listening review: {type(error).__name__}"
            LOG.warning("%s: %s", scenes[0].scene_id, scene_warning)
        counts = [span[-1][1] for span in record["display_spans"]]
        if len(measured) != sum(counts):
            raise ValueError("aligned tokenization does not cover exact spoken narration")
        boundaries = [0.0]
        offset = 0
        for count in counts[:-1]:
            previous_end, next_start = measured[offset + count - 1].end_seconds, measured[offset + count].start_seconds
            if next_start < previous_end - .025:
                raise ValueError("speech group scene boundary overlaps a spoken word")
            boundaries.append(max(boundaries[-1], min(duration, (previous_end + next_start) / 2)))
            offset += count
        boundaries.append(duration)
        offset = 0
        for local_index, scene in enumerate(scenes):
            low, high = boundaries[local_index:local_index + 2]
            segment = audio[round(low * sr):round(high * sr)].copy()
            if not len(segment):
                raise ValueError("speech group produced an empty scene")
            # A grouped utterance must be split to retain the reviewed scene tail.
            # Taper only the two sides of that new cut; an abrupt nonzero sample
            # at the join can click even when the alignment lies between words.
            taper = min(round(.004 * sr), len(segment) // 2)
            if local_index and taper:
                segment[:taper] *= np.linspace(0, 1, taper, endpoint=True)
            if local_index < len(scenes) - 1 and taper:
                segment[-taper:] *= np.linspace(1, 0, taper, endpoint=True)
            spans = tuple(tuple(span) for span in record["display_spans"][local_index])
            local_measured = measured[offset:offset + counts[local_index]]
            mapped = collapse_alignment(local_measured, spans)
            words = tuple(Word(cursor + max(0.0, start - low), cursor + min(len(segment) / sr, end - low))
                          for start, end in mapped)
            voice_end = cursor + len(segment) / sr
            end = voice_end + tail
            timings.append(SceneTiming(cursor, end, words, method, voice_end))
            sf.write(output / f"voice-{scene_index:02d}.wav", segment, sr, subtype="PCM_16")
            resampled = np.interp(np.arange(round(len(segment) * 48000 / sr)) * sr / 48000,
                                  np.arange(len(segment)), segment).astype(np.float32)
            pieces.append((round(cursor * 48000), resampled))
            if scene_warning:
                warnings.append({"scene_id": scene.scene_id, "warning": scene_warning})
            cursor = end
            offset += counts[local_index]
            scene_index += 1
    if scene_index != len(topic.scenes):
        raise ValueError("voice groups omitted reviewed scenes")
    timeline = Timeline(topic, tuple(timings))
    voice = np.zeros(round(timeline.duration * 48000), np.float32)
    for start, audio in pieces:
        voice[start:start + len(audio)] = audio
    sf.write(output / "narration.wav", voice, 48000, subtype="PCM_24")
    (output / "timeline.json").write_text(json.dumps({
        "duration": timeline.duration, "scenes": [asdict(t) for t in timings], "warnings": warnings,
        "alignment_model_sha256": aligner.model_sha256 if aligner else None,
        "topic_sha256": file_hash(output / "topic.json"),
        "speech_profile_sha256": manifest["profile_sha256"],
        "narration_sha256": file_hash(output / "narration.wav"),
    }, indent=2) + "\n")


def prepare(topic: ShortsTopic, output: Path, *, config: Path, alignment_model: Path,
            voice="af_bella", cancelled=lambda: False):
    output.mkdir(parents=True, exist_ok=True)
    topic_path = output / "topic.json"
    topic_path.write_text(topic.model_dump_json(indent=2) + "\n")
    common = [sys.executable, "-m", __name__, "--topic", str(topic_path),
              "--output", str(output), "--config", str(config),
              "--alignment-model", str(alignment_model), "--voice", voice]
    # Each process exits before loading the other model, limiting live RAM.
    for stage in ("synthesize", "align"):
        checked([*common, "--stage", stage], deadline=time.monotonic() + 600, cancelled=cancelled)
    data = json.loads((output / "timeline.json").read_text())
    timings = tuple(SceneTiming(row["start"], row["end"], tuple(Word(**w) for w in row["words"]),
                                row["alignment"], row["voice_end"]) for row in data["scenes"])
    return Timeline(topic, timings)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--topic", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--alignment-model", type=Path, required=True)
    parser.add_argument("--voice", default="af_bella")
    parser.add_argument("--stage", choices=("synthesize", "align"), required=True)
    args = parser.parse_args()
    topic = ShortsTopic.model_validate_json(args.topic.read_text())
    args.output.mkdir(parents=True, exist_ok=True)
    if args.stage == "synthesize":
        synthesize(topic, load_settings(args.config), args.output, args.voice)
    else:
        pacing = load_settings(args.config).pipeline.reference_short
        align(topic, args.output, args.alignment_model, pacing.scene_tail_seconds, pacing=pacing)


if __name__ == "__main__":
    main()
