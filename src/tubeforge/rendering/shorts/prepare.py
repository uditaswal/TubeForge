"""Native speech preparation; heavy TTS and alignment run sequentially.

This module does not approve content. The application must bind and approve the
topic before calling it. The CLI also supports explicitly labelled test data.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
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
from .timeline import SceneTiming, Timeline, Word

LOG = logging.getLogger(__name__)


def synthesize(topic, settings, output, voice):
    primary = KokoroVoiceProvider(settings.pipeline.kokoro)
    fallback = PiperVoiceProvider(settings.pipeline.piper)
    records = []
    for index, scene in enumerate(topic.scenes):
        request = VoiceRequest(text=scene.vo, language="en", voice_id=voice, section_id=scene.scene_id)
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
        path = output / f"voice-{index:02d}.wav"
        sf.write(path, audio, sr, subtype="PCM_16")
        records.append({"scene_id": scene.scene_id, "file": path.name, "sha256": file_hash(path),
                        "provider": result.provider_name, "warning": warning,
                        "duration": len(audio) / sr})
    (output / "voice-manifest.json").write_text(json.dumps(records, indent=2) + "\n")


def align(topic, output, model_path):
    records = json.loads((output / "voice-manifest.json").read_text())
    warning = None
    try:
        aligner = LocalWhisperDTWAligner(model_path=model_path, model_sha256=alignment_model_sha256(model_path))
    except (ProviderValidationError, OSError) as error:
        aligner = None
        warning = f"Forced alignment unavailable; estimated timing: {type(error).__name__}"
        LOG.warning(warning)
    timings, pieces, cursor, warnings = [], [], 0.0, []
    for scene, record in zip(topic.scenes, records, strict=True):
        path = output / record["file"]
        if file_hash(path) != record["sha256"] or record["scene_id"] != scene.scene_id:
            raise ValueError("voice manifest no longer matches scene audio")
        audio, sr = sf.read(path, dtype="float32")
        duration = len(audio) / sr
        # The shared word tokenizer splits "3.4" into two words; joining decimals with
        # an apostrophe keeps one token per whitespace-separated spoken word.
        kwargs = dict(audio_path=path, text=re.sub(r"(?<=\d)[.,](?=\d)", "\u2019", scene.vo), phrase_id=scene.scene_id,
                      section_id=scene.scene_id, phrase_start_seconds=0,
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
            LOG.warning("%s: %s", scene.scene_id, scene_warning)
        if len(measured) != len(scene.vo.split()):
            raise ValueError("aligned tokenization does not map to exact scene narration")
        words = tuple(Word(cursor + w.start_seconds, cursor + w.end_seconds) for w in measured)
        voice_end = cursor + duration
        end = voice_end + .35
        timings.append(SceneTiming(cursor, end, words, method, voice_end))
        # Local PCM resampling is deterministic and requires no remote service.
        resampled = np.interp(np.arange(round(duration * 48000)) * sr / 48000,
                              np.arange(len(audio)), audio).astype(np.float32)
        pieces.append((round(cursor * 48000), resampled))
        if scene_warning:
            warnings.append({"scene_id": scene.scene_id, "warning": scene_warning})
        cursor = end
    timeline = Timeline(topic, tuple(timings))
    voice = np.zeros(round(timeline.duration * 48000), np.float32)
    for start, audio in pieces:
        voice[start:start + len(audio)] = audio
    sf.write(output / "narration.wav", voice, 48000, subtype="PCM_24")
    (output / "timeline.json").write_text(json.dumps({
        "duration": timeline.duration, "scenes": [asdict(t) for t in timings], "warnings": warnings,
        "alignment_model_sha256": aligner.model_sha256 if aligner else None,
        "topic_sha256": file_hash(output / "topic.json"),
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
        align(topic, args.output, args.alignment_model)


if __name__ == "__main__":
    main()
