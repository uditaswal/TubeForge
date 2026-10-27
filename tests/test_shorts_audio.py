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


def test_every_budgeted_cue_has_a_licensed_manifest_entry():
    for name in {name for takes in sfx.TAKES.values() for name in takes}:
        assert name in sfx._MANIFEST
        assert (sfx.SFX_ROOT / sfx._MANIFEST[name]["file"]).is_file()


def test_scheduler_prioritizes_payoff_and_caps_thirty_seconds():
    starts = (0, 3, 7, 11, 15, 19, 23, 27)
    templates = ("hook", "flow", "big_stat", "terminal", "big_stat", "terminal", "flow", "loop")
    placed, dropped = sfx.schedule(starts, templates, 30, hard_topic_changes=frozenset({1, 6}))
    assert len(placed) == 2
    assert [c["cause"] for c in placed] == ["number", "payoff"]
    assert any(c["reason"] == "rate_cap" for c in dropped)
    assert all(c["cause"] != "whoosh" or c["scene_index"] in {1, 6} for c in placed)


def test_scheduler_spacing_reveal_alignment_and_final_exemption():
    starts = (0, 7, 15, 23, 31, 39, 45, 51, 57)
    templates = ("hook", "big_stat", "terminal", "big_stat", "flow", "terminal", "flow", "big_stat", "loop")
    reveal = tuple(v + .5 for v in starts)
    placed, _ = sfx.schedule(starts, templates, 60, reveal_times=reveal,
                             max_per_minute=4, min_gap_s=8)
    assert len(placed) <= 4
    nonfinal = [c for c in placed if c["cause"] != "payoff"]
    assert all(b["at_seconds"] - a["at_seconds"] >= 8 for a, b in zip(nonfinal, nonfinal[1:]))
    assert any(c["at_seconds"] == 7.5 for c in placed)
    close, _ = sfx.schedule((0, 25, 28), ("hook", "big_stat", "loop"), 30)
    assert [c["cause"] for c in close] == ["number", "payoff"]


def test_scheduler_no_repeat_deterministic_and_cuts_silent():
    starts = (0, 8, 16, 24, 32, 40, 48, 56, 64)
    templates = ("hook", "big_stat", "flow", "big_stat", "flow", "terminal", "checklist", "terminal", "loop")
    first = sfx.schedule(starts, templates, 70, max_per_minute=8)
    assert first == sfx.schedule(starts, templates, 70, max_per_minute=8)
    names = [c["cue"] for c in first[0]]
    assert all(a != b for a, b in zip(names, names[1:]))
    assert not any(c["scene_index"] in {2, 4, 6} for c in first[0])


def test_whoosh_requires_explicit_topic_change_and_ten_second_gap():
    starts = (0, 5, 12, 19, 26, 33, 40, 47, 54)
    templates = ("hook", "flow", "flow", "flow", "flow", "flow", "flow", "flow", "loop")
    placed, dropped = sfx.schedule(starts, templates, 60, hard_topic_changes=frozenset({1, 2, 3}),
                                    max_per_minute=10)
    assert [c["scene_index"] for c in placed if c["cause"] == "whoosh"] == [1, 3]
    assert any(c["scene_index"] == 2 and c["reason"] == "whoosh_gap" for c in dropped)


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


def test_sfx_can_be_explicitly_turned_off(tmp_path):
    """A caller that explicitly opts out (e.g. a future per-job preference) gets voice + music
    only, with a literally silent effects track, not just a quiet one."""
    narration = _synthetic_narration(tmp_path, 30.0)
    scene_starts = (0.0, 4.0, 9.0, 14.0, 19.0, 24.0, 28.0)
    templates = ("hook", "big_stat", "before_after", "flow", "checklist", "terminal", "loop")

    mix = master(narration, scene_starts, tmp_path / "mix", templates=templates, title="Railway breach", sfx_enabled=False)

    provenance = json.loads((mix.parent / "audio-provenance.json").read_text())
    assert provenance["sfx_enabled"] is False
    assert provenance["sound_effects"] == []
    effects_track = sf.read(mix.parent / "effects.wav", dtype="float32")[0]
    assert np.max(np.abs(effects_track)) == 0.0  # literally silent, not just quiet


def test_master_places_budgeted_cues_and_riser_by_default(tmp_path):
    narration = _synthetic_narration(tmp_path, 30.0)
    scene_starts = (0.0, 4.0, 9.0, 14.0, 19.0, 24.0, 28.0)
    templates = ("hook", "big_stat", "before_after", "flow", "checklist", "terminal", "loop")

    mix = master(narration, scene_starts, tmp_path / "mix", templates=templates, title="Railway breach")

    assert mix.is_file()
    provenance = json.loads((mix.parent / "audio-provenance.json").read_text())
    assert provenance["sfx_enabled"] is True
    assert provenance["music"]["mood"] in {name for name, *_ in MOODS}
    cues = provenance["sound_effects"]
    assert [c["template"] for c in cues] == ["big_stat", "loop"]
    assert [c["cue"] for c in cues] == ["pop", sfx.RISER_CUE]
    assert provenance["sound_effect_peak"] == .18
    assert provenance["sound_effects_dropped"]
    effects = sf.read(mix.parent / "effects.wav", dtype="float32")[0]
    assert np.max(np.abs(effects)) <= .18 + 1e-5
    assert provenance["mastered_measurement"]["input_tp"] <= -1.5
    assert abs(provenance["mastered_measurement"]["input_i"] - (-14)) <= 1.0


def test_master_is_byte_deterministic_for_same_title_and_scenes(tmp_path):
    from tubeforge.rendering.shorts.encode import file_hash
    narration = _synthetic_narration(tmp_path, 30.0)
    options = {"templates": ("hook", "big_stat", "flow", "terminal", "loop"),
               "title": "Same topic", "reveal_times": (0, 6, 12, 18, 27)}
    starts = (0, 5, 11, 17, 27)
    first = master(narration, starts, tmp_path / "first", **options)
    second = master(narration, starts, tmp_path / "second", **options)
    assert file_hash(first) == file_hash(second)
    assert json.loads((first.parent / "audio-provenance.json").read_text())["sound_effects"] == \
           json.loads((second.parent / "audio-provenance.json").read_text())["sound_effects"]


def test_master_bed_none_mixes_real_silence_not_the_synthesized_default(tmp_path):
    """Before this, "No background music" did nothing — every render got the synthesized bed
    regardless of selection (video-quality review §4.5 / operator finding, 26 Oct)."""
    narration = _synthetic_narration(tmp_path, 26.0)
    scene_starts = (0.0, 4.0, 9.0, 14.0, 19.0, 24.0)
    templates = ("hook", "big_stat", "before_after", "flow", "checklist", "loop")

    mix = master(narration, scene_starts, tmp_path / "mix", templates=templates, title="Railway breach", bed=None)

    bed_track = sf.read(mix.parent / "music-ducked.wav", dtype="float32")[0]
    assert np.max(np.abs(bed_track)) == 0.0  # literally no music, not a quiet synth bed
    provenance = json.loads((mix.parent / "audio-provenance.json").read_text())
    assert provenance["music"] == {"mode": "silence"}
    assert "mastered_measurement" in provenance  # narration + SFX still mastered normally


def test_master_bed_path_mixes_the_real_track_not_a_synthesized_one(tmp_path):
    narration = _synthetic_narration(tmp_path, 26.0)
    scene_starts = (0.0, 4.0, 9.0, 14.0, 19.0, 24.0)
    templates = ("hook", "big_stat", "before_after", "flow", "checklist", "loop")
    track_sr = SR
    track = (np.sin(2 * np.pi * 330 * np.arange(track_sr * 40) / track_sr)).astype(np.float32)
    track_path = tmp_path / "track.wav"
    sf.write(track_path, track, track_sr, subtype="PCM_16")

    mix = master(narration, scene_starts, tmp_path / "mix", templates=templates, title="Railway breach", bed=track_path)

    provenance = json.loads((mix.parent / "audio-provenance.json").read_text())
    assert provenance["music"]["mode"] == "track"
    assert provenance["music"]["source_path"] == str(track_path)
    from tubeforge.rendering.shorts.encode import file_hash
    assert provenance["music"]["source_sha256"] == file_hash(track_path)
    bed_track = sf.read(mix.parent / "music-ducked.wav", dtype="float32")[0]
    assert np.max(np.abs(bed_track)) > 0  # the real track is actually audible


def test_master_rejects_a_template_count_mismatch(tmp_path):
    narration = _synthetic_narration(tmp_path, 26.0)
    with pytest.raises(ValueError, match="templates must name every scene"):
        master(narration, (0.0, 4.0, 9.0), tmp_path / "mix", templates=("hook", "big_stat"), title="t")


def test_reference_short_render_passes_templates_and_title(monkeypatch, tmp_path):
    from tubeforge.pipeline import reference_short
    from tubeforge.core.config import ReferenceShortConfig
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

    def fake_master(narration, scene_starts, output, *, templates, title, bed="synthesized", sfx_enabled=True,
                    sfx_max_per_minute=4, sfx_min_gap_s=6.0, sfx_peak=.18, reveal_times=None,
                    cancelled=lambda: False, ffmpeg="ffmpeg"):
        captured["templates"] = templates
        captured["title"] = title
        captured["bed"] = bed
        captured["sfx_enabled"] = sfx_enabled
        captured["budget"] = (sfx_max_per_minute, sfx_min_gap_s, sfx_peak)
        captured["reveal_times"] = reveal_times
        output.mkdir(parents=True, exist_ok=True)
        (output / "audio-provenance.json").write_text(json.dumps({"narration_health": {}}))
        return output / "mix.wav"

    monkeypatch.setattr(reference_short, "master", fake_master)
    monkeypatch.setattr(reference_short, "encode", lambda *a, **k: {"passed": True})
    monkeypatch.setattr(reference_short, "load_plates", lambda *a, **k: (None, ()))
    (tmp_path / "narration.wav").write_bytes(b"x")

    reference_short.render(timeline, tmp_path, tmp_path / "out.mp4",
                           ReferenceShortConfig(budget_realtime_factor=10.0),
                           draft=True, cancelled=lambda: False)

    assert captured["title"] == topic.title
    assert captured["templates"] == tuple(s.template for s in topic.scenes)
    assert captured["bed"] == "synthesized"  # default: unchanged behavior for a caller that picks no track
    assert captured["sfx_enabled"] is True  # default: on, per the operator's 27 Oct preference
    assert captured["budget"] == (4, 6.0, .18)
    assert captured["reveal_times"][1] == timings[1].words[topic.scenes[1].reveal_words[0]].start


def test_reference_sfx_config_defaults():
    from tubeforge.core.config import ReferenceShortConfig
    config = ReferenceShortConfig()
    assert (config.sfx.max_per_minute, config.sfx.min_gap_s, config.sfx.peak) == (4, 6.0, .18)
