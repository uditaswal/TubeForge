"""Reference music algorithm, speech ducking and measured two-pass mastering."""
from __future__ import annotations

import json
from pathlib import Path
import time

import numpy as np
import soundfile as sf

from tubeforge.rendering.loudness import analyze
from .encode import checked, file_hash

SR = 48000


def synth_music(count):
    """Original reference pad/bass/plucks; no external sampled recording."""
    progression = ((57, (57, 60, 64)), (53, (53, 57, 60)),
                   (48, (48, 52, 55)), (55, (55, 59, 62)))
    music = np.zeros(count, np.float32)
    beat, bar = 60 / 96, 4 * 60 / 96
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
        for eighth in range(8):
            offset = start + round(eighth * beat * SR / 2)
            length = min(round(.35 * SR), count - offset)
            if length > 0:
                x = np.arange(length, dtype=np.float32) / SR
                music[offset:offset + length] += (np.sin(2 * np.pi * hz(notes[eighth % 3] + 12) * x) *
                                                 np.exp(-9 * x) * .28).astype(np.float32)
    seconds = np.arange(count, dtype=np.float32) / SR
    music *= np.minimum(seconds, 1) * np.minimum((count / SR - seconds) / 1.2, 1)
    return music * (.12 / max(float(np.max(np.abs(music))), 1e-6))


def master(narration: Path, scene_starts: tuple[float, ...], output: Path, *,
           cancelled=lambda: False, ffmpeg="ffmpeg"):
    """Mix locally, retain separate stems, then leave AAC true-peak headroom."""
    voice, sample_rate = sf.read(narration, dtype="float32")
    if sample_rate != SR or voice.ndim != 1 or not 25 <= len(voice) / SR <= 45 or not np.isfinite(voice).all():
        raise ValueError("mastering requires finite mono 48 kHz narration, 25–45 seconds")
    peak = float(np.max(np.abs(voice)))
    if peak < .001:
        raise ValueError("cannot master silent narration")
    output.mkdir(parents=True, exist_ok=True)
    voice = voice * (.75 / peak)
    n = len(voice)
    bed, effects = synth_music(n), np.zeros(n, np.float32)
    levels = np.array([np.sqrt(np.mean(voice[i:i + 480] ** 2)) for i in range(0, n, 480)])
    smooth = np.convolve(levels, np.ones(15) / 15, mode="same")
    duck = np.interp(np.arange(n) / 480, np.arange(len(smooth)), 1 - .75 * np.clip(smooth / .08, 0, 1))
    bed *= duck
    rng = np.random.default_rng(20261021)
    for at in scene_starts[1:]:
        start = max(0, round((at - .035) * SR))
        count = min(round(.18 * SR), n - start)
        if count <= 0:
            raise ValueError("scene sound cue exceeds audio duration")
        envelope = np.sin(np.linspace(0, np.pi, count)) ** 2
        noise = np.convolve(rng.normal(0, 1, count), np.ones(24) / 24, mode="same")
        effects[start:start + count] += (noise * envelope * .035).astype(np.float32)
    mix = voice + bed + effects
    for name, samples in (("music-ducked", bed), ("effects", effects), ("mix-raw", mix)):
        sf.write(output / f"{name}.wav", samples, SR, subtype="FLOAT")
    deadline = time.monotonic() + 240
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
    provenance = {"algorithm": "reference pad, bass, eighth-note plucks and filtered-noise scene accents",
                  "origin": "Original synthesized signals, no sampled recording",
                  "bpm": 96, "music_peak_before_duck": .12, "speech_duck_maximum": .75,
                  "master_target_lufs": -14, "master_target_dbtp": -2.5,
                  "input_measurement": measured, "mastered_measurement": result, "mastering": "gain-matched true-peak limiter, up to 3 measured passes", "narration_sha256": file_hash(narration),
                  "mix_sha256": file_hash(final),
                  "rights_note": "Synthesis does not establish voice/model/font licensing; retain their provenance separately."}
    (output / "audio-provenance.json").write_text(json.dumps(provenance, indent=2) + "\n")
    return final
