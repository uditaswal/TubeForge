"""Reference music algorithm, speech ducking and measured two-pass mastering."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import time

import numpy as np
import soundfile as sf

from tubeforge.rendering.loudness import analyze
from . import sfx
from .audio_health import scan_wav
from .encode import checked, file_hash
from .schema import REFERENCE_SHORT_MAX_SECONDS, REFERENCE_SHORT_MIN_SECONDS

SR = 48000

# Four distinct chord-progression/tempo/density moods so every topic does not share the
# identical bed (video-quality review §1, §4.5: "the same four-chord sine pad... under
# every video"). Chosen deterministically from the topic title so a render is reproducible.
# Each entry: (name, bpm, plucks_per_bar, ((root_midi, (triad_midis...)), ...) four bars).
MOODS = (
    ("steady", 96, 8, ((57, (57, 60, 64)), (53, (53, 57, 60)), (48, (48, 52, 55)), (55, (55, 59, 62)))),
    ("driving", 112, 8, ((52, (52, 55, 59)), (48, (48, 52, 55)), (55, (55, 59, 62)), (50, (50, 54, 57)))),
    ("moody", 84, 4, ((50, (50, 53, 57)), (46, (46, 50, 53)), (53, (53, 57, 60)), (48, (48, 52, 55)))),
    ("bright", 104, 8, ((48, (48, 52, 55)), (55, (55, 59, 62)), (57, (57, 60, 64)), (53, (53, 57, 60)))),
)


def mood_for(title: str) -> tuple[str, int, int, tuple]:
    """Deterministic mood pick from the topic title — reproducible, not random per render."""
    digest = hashlib.sha256(title.encode()).hexdigest()
    return MOODS[int(digest[:8], 16) % len(MOODS)]


def synth_music(count: int, title: str) -> tuple[np.ndarray, dict]:
    """Original reference pad/bass/plucks; no external sampled recording.

    One of four moods (progression, tempo, pluck density) is picked deterministically from
    the topic title, so videos on different topics no longer share one identical bed.
    """
    name, bpm, plucks_per_bar, progression = mood_for(title)
    music = np.zeros(count, np.float32)
    beat, bar = 60 / bpm, 4 * 60 / bpm
    hz = lambda midi: 440 * 2 ** ((midi - 69) / 12)
    for index, start_seconds in enumerate(np.arange(0, count / SR, bar)):
        start = round(start_seconds * SR)
        n = min(round(bar * SR), count - start)
        t = np.arange(n, dtype=np.float32) / SR
        root, notes = progression[index % len(progression)]
        envelope = np.minimum(t / .4, 1) * np.clip((bar - t) / .5, 0, 1)
        pad = sum(np.sin(2 * np.pi * hz(note + 12) * t) +
                  .4 * np.sin(2 * np.pi * hz(note + 12) * 2.003 * t) for note in notes) / 3
        bass = np.sin(2 * np.pi * hz(root - 12) * t) * .9
        music[start:start + n] += ((pad + bass) * .25 * envelope).astype(np.float32)
        for pluck in range(plucks_per_bar):
            offset = start + round(pluck * beat * SR * 4 / plucks_per_bar)
            length = min(round(.35 * SR), count - offset)
            if length > 0:
                x = np.arange(length, dtype=np.float32) / SR
                music[offset:offset + length] += (np.sin(2 * np.pi * hz(notes[pluck % 3] + 12) * x) *
                                                 np.exp(-9 * x) * .28).astype(np.float32)
    seconds = np.arange(count, dtype=np.float32) / SR
    music *= np.minimum(seconds, 1) * np.minimum((count / SR - seconds) / 1.2, 1)
    normalized = music * (.12 / max(float(np.max(np.abs(music))), 1e-6))
    return normalized, {"mood": name, "bpm": bpm, "plucks_per_bar": plucks_per_bar,
                        "progression_roots": [root for root, _ in progression]}


def master(narration: Path, scene_starts: tuple[float, ...], output: Path, *,
           templates: tuple[str, ...], title: str, cancelled=lambda: False, ffmpeg="ffmpeg"):
    """Mix locally, retain separate stems, then leave AAC true-peak headroom.

    ``templates`` names each scene's template (same order/length as ``scene_starts``);
    ``title`` seeds the music mood. Both come from the topic being rendered, so each cut's
    sound effect has a cause on screen (video-quality review §4.5) instead of the identical
    filtered-noise accent that used to play on every scene change.
    """
    if len(templates) != len(scene_starts):
        raise ValueError("templates must name every scene (one per scene_starts entry)")
    voice, sample_rate = sf.read(narration, dtype="float32")
    if sample_rate != SR or voice.ndim != 1 or not REFERENCE_SHORT_MIN_SECONDS <= len(voice) / SR <= REFERENCE_SHORT_MAX_SECONDS or not np.isfinite(voice).all():
        raise ValueError("mastering requires finite mono 48 kHz narration, 25–90 seconds")
    peak = float(np.max(np.abs(voice)))
    if peak < .001:
        raise ValueError("cannot master silent narration")
    output.mkdir(parents=True, exist_ok=True)
    voice = voice * (.75 / peak)
    n = len(voice)
    deadline = time.monotonic() + 240
    bed, music_provenance = synth_music(n, title)
    effects = np.zeros(n, np.float32)
    levels = np.array([np.sqrt(np.mean(voice[i:i + 480] ** 2)) for i in range(0, n, 480)])
    smooth = np.convolve(levels, np.ones(15) / 15, mode="same")
    duck = np.interp(np.arange(n) / 480, np.arange(len(smooth)), 1 - .75 * np.clip(smooth / .08, 0, 1))
    bed *= duck
    cues_placed = []
    for index, at in enumerate(scene_starts[1:], start=1):
        template = templates[index]
        cue_name = sfx.cue_for_template(template)
        cue = sfx.load(cue_name, SR, ffmpeg=ffmpeg, deadline=deadline, cancelled=cancelled)
        # A short cue starts just before the cut, matching the previous noise accent's
        # timing (peak lands a touch after the visual, per the sound guide). The riser
        # (cta/loop payoff) instead crests exactly on the cut, so it starts (its own
        # length) earlier, clipped at 0 if there isn't that much lead time.
        start = round((at - (len(cue) / SR if cue_name == sfx.RISER_CUE else .035)) * SR)
        sfx.place(effects, cue, start)
        cues_placed.append({"scene_index": index, "template": template, "cue": cue_name,
                            "at_seconds": at})
    mix = voice + bed + effects
    for name, samples in (("music-ducked", bed), ("effects", effects), ("mix-raw", mix)):
        sf.write(output / f"{name}.wav", samples, SR, subtype="FLOAT")
    raw = output / "mix-raw.wav"
    # Speech peaks cap plain linear loudnorm near -16 LUFS. Match loudness with a
    # true-peak limiter in the chain: measure, apply gain+limiter, re-measure and
    # correct (at most three passes), so -14 LUFS holds under the -2.5 dBTP ceiling.
    measured = analyze(raw, ffmpeg=ffmpeg, deadline=deadline, cancelled=cancelled, poll_seconds=.1,
                       target_i=-14, target_tp=-2.5, target_lra=9)
    gain = -14 - float(measured["input_i"])
    final = output / "mix.wav"
    temporary = output / "mix.pending.wav"
    result = measured
    try:
        for attempt in range(3):
            checked([ffmpeg, "-y", "-v", "error", "-i", str(raw), "-af",
                     f"volume={gain:.2f}dB,alimiter=limit=0.74:attack=5:release=60:level=disabled",
                     "-ar", str(SR), "-c:a", "pcm_s24le", str(temporary)],
                    deadline=deadline, cancelled=cancelled)
            result = analyze(temporary, ffmpeg=ffmpeg, deadline=deadline, cancelled=cancelled, poll_seconds=.1,
                             target_i=-14, target_tp=-2.5, target_lra=9)
            error = -14 - float(result["input_i"])
            if abs(error) <= .3 and float(result["input_tp"]) <= -2.4:
                break
            gain += error
        if cancelled():
            raise RuntimeError("mastering cancelled before promotion")
        temporary.replace(final)
    finally:
        temporary.unlink(missing_ok=True)
    provenance = {"algorithm": "mood-varied synthesized pad/bass/plucks bed plus licensed scene-cause sound effects",
                  "origin": "Music: original synthesized signals, no sampled recording. "
                            "Sound effects: Pixabay Content License, see assets/sfx/LICENSE-pixabay.md",
                  "music": music_provenance, "music_peak_before_duck": .12, "speech_duck_maximum": .75,
                  "sound_effects": cues_placed, "sound_effect_peak": sfx.CUE_PEAK,
                  "master_target_lufs": -14, "master_target_dbtp": -2.5,
                  "input_measurement": measured, "mastered_measurement": result, "mastering": "gain-matched true-peak limiter, up to 3 measured passes", "narration_sha256": file_hash(narration),
                  "mix_sha256": file_hash(final),
                  "rights_note": "Synthesis does not establish voice/model/font licensing; retain their provenance separately. "
                                 "Sound effects carry the Pixabay Content License named above, independent of voice/font/model licensing."}
    provenance["narration_health"] = scan_wav(narration, scene_starts=scene_starts)
    (output / "audio-provenance.json").write_text(json.dumps(provenance, indent=2) + "\n")
    return final
