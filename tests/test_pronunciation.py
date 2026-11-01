"""Pronunciation check: expected spoken text versus what a speech model hears (fake transcribers only)."""
import json
from types import SimpleNamespace

from tubeforge.pipeline import pronunciation as pr
from tubeforge.rendering.shorts import prepare


def test_numbers_are_compared_as_words():
    assert pr.normalize("Version 2.15.0 and 93% in 2013") == ["version", "two", "fifteen", "zero", "and", "ninety", "three", "percent", "in", "two", "thousand", "thirteen"]
    assert pr.normalize("double-you’s") == ["double", "you's"]
    assert pr.normalize("$12 and 50%") == ["twelve", "dollars", "and", "fifty", "percent"]


def test_identical_and_trivially_different_text_has_no_suspects():
    spoken = "One expression, jay en dee eye, can point at a you ar el."
    clean = pr.compare(pr.expected_tokens(spoken), "One expression, jay en dee eye, can point at a you ar el.")
    assert clean["suspects"] == [] and clean["match_ratio"] == 1.0
    digits = pr.compare(pr.expected_tokens("it hit ninety three percent of cloud"), "It hit 93% of cloud")
    assert digits["suspects"] == []                                  # "93%" == "ninety three percent"
    tiny = pr.compare(pr.expected_tokens("point at a url"), "point at uh url")
    assert tiny["suspects"] == []                                    # one-letter articles are ignored


def test_a_mispronounced_acronym_is_flagged_with_expected_and_heard():
    result = pr.compare(pr.expected_tokens("expression jay en dee eye can point"), "expression gindy can point")
    assert [s["expected"] for s in result["suspects"]] == ["jay en dee eye"]
    assert result["suspects"][0]["heard"] == "gindy" and result["suspects"][0]["similarity"] < pr.MIN_SIMILARITY
    missing = pr.compare(pr.expected_tokens("loads data via el dap now"), "loads data now")
    assert any(s["heard"] == "(nothing)" for s in missing["suspects"])


def test_suspects_map_back_to_display_words():
    spoken = "One expression, jay en dee eye, can point"
    display = "One expression, JNDI, can point".split()
    spans = [(0, 1), (1, 2), (2, 6), (6, 7), (7, 8)]
    result = pr.check_group(spoken_text=spoken, display_words=display, display_spans=spans, transcribe=lambda: "One expression, gindy, can point")
    assert result["suspects"][0]["display"] == ["JNDI"]


def _manifest(tmp_path, spoken):
    return {"groups": [{"scene_ids": ["s1"], "spoken_text": spoken, "file": "voice-group-00.wav",
                        "display_spans": [[[0, 1], [1, 5], [5, 6], [6, 7]]]}]}


def test_report_is_written_with_suspects_and_never_raises(tmp_path, monkeypatch):
    topic = SimpleNamespace(scenes=[SimpleNamespace(scene_id="s1", vo="Use JNDI wisely now")])
    pacing = SimpleNamespace(pronunciation_check="advisory", ffmpeg_executable="ffmpeg")
    manifest = _manifest(tmp_path, "Use jay en dee eye wisely now")
    aligner = SimpleNamespace(model=object())
    monkeypatch.setattr(pr, "transcribe_with", lambda model, path, ffmpeg="ffmpeg": "Use gindy wisely now")
    report = prepare.pronunciation_report(topic, tmp_path, manifest, aligner, pacing)
    assert report["suspect_count"] == 1
    saved = json.loads((tmp_path / "pronunciation-report.json").read_text())
    assert saved["groups"][0]["suspects"][0]["display"] == ["JNDI"] and saved["groups"][0]["suspects"][0]["scene_id"] == "s1"
    monkeypatch.setattr(pr, "transcribe_with", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("model blew up")))
    (tmp_path / "pronunciation-report.json").unlink()
    assert prepare.pronunciation_report(topic, tmp_path, manifest, aligner, pacing) is None   # advisory: no exception
    assert not (tmp_path / "pronunciation-report.json").exists()


def test_check_is_skipped_when_off_or_without_a_model(tmp_path):
    topic = SimpleNamespace(scenes=[])
    assert prepare.pronunciation_report(topic, tmp_path, {"groups": []}, None, SimpleNamespace(pronunciation_check="advisory")) is None
    assert prepare.pronunciation_report(topic, tmp_path, {"groups": []}, object(), SimpleNamespace(pronunciation_check="off")) is None


def test_a_dropped_leading_letter_is_still_caught_but_a_written_form_match_is_not():
    spoken = "We call the eh pee eye every day"
    display = "We call the API every day".split()
    spans = [(0, 1), (1, 2), (2, 3), (3, 6), (6, 7), (7, 8)]
    garbled = pr.check_group(spoken_text=spoken, display_words=display, display_spans=spans, transcribe=lambda: "We call the PI every day")
    assert [s["display"] for s in garbled["suspects"]] == [["API"]]            # the old "A P I" failure: heard "PI"
    fine = pr.check_group(spoken_text=spoken, display_words=display, display_spans=spans, transcribe=lambda: "We call the API every day.")
    assert fine["suspects"] == []
