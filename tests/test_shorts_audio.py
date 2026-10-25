"""Mood-varied music and licensed scene-cause sound effects (video-quality review §4.5).

Replaces the single synthesized chord progression and the near-inaudible filtered-noise
scene accent: every topic now picks one of four moods deterministically from its title, and
every scene cut plays a real, licensed sound effect chosen by the destination scene's
template instead of the same noise burst everywhere.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from tubeforge.rendering.shorts import sfx
from tubeforge.rendering.shorts.audio import SR, MOODS, master, mood_for, synth_music

pytestmark = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="FFmpeg required for real audio mastering")


def test_mood_is_deterministic_and_covers_every_mood():
    assert mood_for("Railway breach") == mood_for("Railway breach")
    titles = [f"topic {i} with some distinguishing words about a subject" for i in range(200)]
    seen = {mood_for(t)[0] for t in titles}
    assert seen == {name for name, *_ in MOODS}, "200 varied titles should hit all four moods"


def test_synth_music_differs_by_mood_but_is_reproducible():
    a1, meta_a1 = synth_music(SR * 20, "Railway breach")
    a2, meta_a2 = synth_music(SR * 20, "Railway breach")
    b, meta_b = synth_music(SR * 20, "Completely different topic entirely")
    assert np.array_equal(a1, a2) and meta_a1 == meta_a2, "same title must render identical audio"
    assert meta_a1["mood"] != meta_b["mood"] or not np.array_equal(a1, b)
    assert np.max(np.abs(a1)) <= 0.12 + 1e-6


def test_cue_for_template_has_a_cause_and_riser_is_reserved_for_the_payoff():
    assert sfx.cue_for_template("big_stat") == "pop"
    assert sfx.cue_for_template("checklist") == "click"
    assert sfx.cue_for_template("terminal") == "key-press"
    assert sfx.cue_for_template("cta") == sfx.RISER_CUE
    assert sfx.cue_for_template("loop") == sfx.RISER_CUE
    assert sfx.cue_for_template("some-future-template") == sfx.FALLBACK_CUE
    # Every named cue must resolve to a real, vendored, licensed file.
    for name in {*sfx.CUE_BY_TEMPLATE.values(), sfx.FALLBACK_CUE, sfx.RISER_CUE}:
        assert name in sfx._MANIFEST
        assert (sfx.SFX_ROOT / sfx._MANIFEST[name]["file"]).is_file()


def test_sfx_manifest_entries_all_carry_a_named_license():
    for entry in sfx._MANIFEST.values():
        assert "Pixabay Content License" in entry["license"]
        assert entry["license"].strip().casefold() not in {"free", "royalty free", "royalty-free", "unknown", "n/a"}


def test_load_decodes_real_file_peak_normalized():
    cue = sfx.load("pop", SR, ffmpeg="ffmpeg", deadline=__import__("time").monotonic() + 30, cancelled=lambda: False)
    assert cue.dtype == np.float32
    assert abs(float(np.max(np.abs(cue))) - 1.0) < 1e-3
    expected_samples = round(sfx._MANIFEST["pop"]["duration_s"] * SR)
    assert abs(len(cue) - expected_samples) < SR * 0.05  # mp3 decode can differ by a few ms


def test_place_trims_a_cue_that_starts_before_zero_and_raises_past_the_end():
    effects = np.zeros(1000, np.float32)
    cue = np.ones(400, np.float32)
    sfx.place(effects, cue, -100)  # riser needing more lead time than available
    assert np.count_nonzero(effects) == 300
    assert effects[0] != 0 and effects[299] != 0 and effects[300] == 0

    with pytest.raises(ValueError, match="at or after the end"):
        sfx.place(np.zeros(10, np.float32), cue, 10)


def _synthetic_narration(tmp_path: Path, duration_s: float) -> Path:
    n = round(duration_s * SR)
    rng = np.random.default_rng(7)
    voice = np.zeros(n, np.float32)
    t = 0
    while t < n - 4000:
        length = int(rng.integers(4000, 12000))
        voice[t:t + length] = rng.normal(0, .08, min(length, n - t)).astype(np.float32)
        t += length + int(rng.integers(1000, 4000))
    path = tmp_path / "narration.wav"
    sf.write(path, voice, SR, subtype="FLOAT")
    return path


def test_master_places_one_real_cue_per_cut_and_riser_on_the_payoff(tmp_path):
    narration = _synthetic_narration(tmp_path, 30.0)
    scene_starts = (0.0, 4.0, 9.0, 14.0, 19.0, 24.0, 28.0)
    templates = ("hook", "big_stat", "before_after", "flow", "checklist", "terminal", "loop")

    mix = master(narration, scene_starts, tmp_path / "mix", templates=templates, title="Railway breach")

    assert mix.is_file()
    provenance = json.loads((mix.parent / "audio-provenance.json").read_text())
    assert provenance["music"]["mood"] in {name for name, *_ in MOODS}
    cues = provenance["sound_effects"]
    assert [c["template"] for c in cues] == list(templates[1:])
    assert [c["cue"] for c in cues] == ["pop", "whoosh-short", "whoosh-short", "click", "key-press", sfx.RISER_CUE]
    assert provenance["mastered_measurement"]["input_tp"] <= -1.5
    assert abs(provenance["mastered_measurement"]["input_i"] - (-14)) <= 1.0


def test_master_rejects_a_template_count_mismatch(tmp_path):
    narration = _synthetic_narration(tmp_path, 26.0)
    with pytest.raises(ValueError, match="templates must name every scene"):
        master(narration, (0.0, 4.0, 9.0), tmp_path / "mix", templates=("hook", "big_stat"), title="t")


def test_reference_short_render_passes_templates_and_title(monkeypatch, tmp_path):
    from tubeforge.pipeline import reference_short
    from tubeforge.rendering.shorts.schema import ShortsTopic
    from tubeforge.rendering.shorts.timeline import SceneTiming, Timeline, Word
    from tests.test_reference_shorts import topic_data

    data = topic_data()
    for scene in data["scenes"]:
        scene["caption"] = scene["vo"]
    topic = ShortsTopic.model_validate(data)
    timings = []
    for i, scene in enumerate(topic.scenes):
        count = len(scene.vo.split())
        step = 3.65 / count
        words = tuple(Word(i * 4 + j * step, i * 4 + (j + 1) * step) for j in range(count))
        timings.append(SceneTiming(i * 4, (i + 1) * 4, words, "synthetic"))
    timeline = Timeline(topic, tuple(timings))

    captured = {}

    def fake_master(narration, scene_starts, output, *, templates, title, cancelled=lambda: False, ffmpeg="ffmpeg"):
        captured["templates"] = templates
        captured["title"] = title
        output.mkdir(parents=True, exist_ok=True)
        (output / "audio-provenance.json").write_text(json.dumps({"narration_health": {}}))
        return output / "mix.wav"

    monkeypatch.setattr(reference_short, "master", fake_master)
    monkeypatch.setattr(reference_short, "encode", lambda *a, **k: {"passed": True})
    monkeypatch.setattr(reference_short, "load_plates", lambda *a, **k: (None, ()))
    (tmp_path / "narration.wav").write_bytes(b"x")

    reference_short.render(timeline, tmp_path, tmp_path / "out.mp4",
                           __import__("types").SimpleNamespace(ffmpeg_executable="ffmpeg",
                                                                ffprobe_executable="ffprobe",
                                                                budget_realtime_factor=10.0),
                           draft=True, cancelled=lambda: False)

    assert captured["title"] == topic.title
    assert captured["templates"] == tuple(s.template for s in topic.scenes)
