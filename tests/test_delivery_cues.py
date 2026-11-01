"""Delivery cues: tag parsing, segment planning, audio effects and cued synthesis."""
from __future__ import annotations

import json
from types import SimpleNamespace

import numpy as np
import pytest
import soundfile as sf

from tubeforge.providers.content.output import bind_reference_output, split_delivery_cues
from tubeforge.rendering.shorts import delivery, prepare
from tubeforge.rendering.shorts.cues import Cue, has_cues, parse
from tubeforge.rendering.shorts.spoken import profile_hash

RATE = 24_000


def test_plain_narration_is_untouched():
    assert parse("Nothing special happens here at all.") == ("Nothing special happens here at all.", ())
    assert not has_cues("Nothing special happens here at all.")


def test_tags_become_clean_text_plus_word_anchored_cues():
    clean, cues = parse("It got *much* worse. [pause 0.4] Nobody noticed [breath] until Friday.")
    assert clean == "It got much worse. Nobody noticed until Friday."
    assert [(c.kind, c.at, c.end, c.seconds) for c in cues] == [
        ("emphasis", 2, 3, None), ("pause", 4, None, 0.4), ("breath", 6, None, None)]


def test_bare_pause_default_and_punctuation_after_markers():
    clean, cues = parse("Then *it broke*. [pause] Why did it break?")
    assert clean == "Then it broke. Why did it break?"
    assert cues[0] == Cue(kind="emphasis", at=1, end=3)
    assert cues[1].kind == "pause" and cues[1].seconds == 0.35


def test_whisper_span_and_punctuation():
    clean, cues = parse("Look closely, [whisper]nobody was watching the logs[/whisper], and it ran.")
    assert clean == "Look closely, nobody was watching the logs, and it ran."
    assert [(c.kind, c.at, c.end) for c in cues] == [("whisper", 2, 7)]


@pytest.mark.parametrize("text", [
    "an *unclosed emphasis here",
    "stray [/whisper] close tag now",
    "one [whisper]two[/whisper] three four",            # whisper too short
    "this *is way too long* for stress",                 # emphasis over two words
    "wait [pause 2.0] what is going on",                 # pause out of range
    "a [pause 0.2] b [pause 0.2] c [pause 0.2] d [pause 0.2] e [pause 0.2] f g",  # over the cue budget
    "mid*word marker",                                   # marker not at a word edge
])
def test_malformed_or_excessive_cues_raise(text):
    with pytest.raises(ValueError):
        parse(text)


def test_edge_pauses_are_dropped():
    clean, cues = parse("[pause 0.5] Hello there friend [pause 0.5]")
    assert clean == "Hello there friend" and cues == ()


def test_bind_degrades_malformed_cues_to_plain_speech_instead_of_rejecting_the_script():
    clean, cues = split_delivery_cues("Wait *what is going on [pause 9] here")
    assert clean == "Wait what is going on here" and cues == []
    clean, cues = split_delivery_cues("It *really* broke. [pause 0.3] Then it healed.")
    assert clean == "It really broke. Then it healed." and [c["kind"] for c in cues] == ["emphasis", "pause"]


def test_bind_writes_clean_narration_and_cues_into_scene_and_section():
    package = {"reference_short": {"scenes": [{"scene_id": "s1", "template": "hook"}]},
               "script_sections": [{"scene_id": "s1", "narration": "It was *quiet*. [breath] Too quiet for a Friday."}]}
    request = SimpleNamespace(sources=[], topic="t")
    bound = bind_reference_output(package, request)
    scene = bound["reference_short"]["scenes"][0]
    assert scene["vo"] == "It was quiet. Too quiet for a Friday."
    assert bound["script_sections"][0]["narration"] == scene["vo"]
    assert [c["kind"] for c in scene["cues"]] == ["emphasis", "breath"]


def test_plan_splits_at_style_changes_pauses_and_breaths():
    tokens = "it was quiet too quiet for a friday".split()
    cues = (Cue(kind="emphasis", at=2, end=3), Cue(kind="pause", at=3, seconds=0.4), Cue(kind="breath", at=6))
    segments = delivery.plan(tokens, cues)
    assert [(s.text, s.style, s.pause_before, s.breath_before) for s in segments] == [
        ("it was", "plain", 0.0, False), ("quiet", "emphasis", 0.0, False),
        ("too quiet for", "plain", 0.4, False), ("a friday", "plain", 0.0, True)]


def _tone(text: str, scale: float) -> np.ndarray:
    count = int(RATE * 0.1 * len(text.split()) / scale)
    return (np.sin(np.linspace(0, 400 * len(text), count)) * .3).astype(np.float32)


def test_render_inserts_the_requested_silence_and_breath():
    segments = delivery.plan("one two three four".split(), (Cue(kind="pause", at=2, seconds=0.5),))
    plain = delivery.render([delivery.Segment("one two three four")], _tone, RATE)
    cued = delivery.render(segments, _tone, RATE)
    assert abs((len(cued) - len(plain)) / RATE - 0.5) < 0.01
    with_breath = delivery.render(delivery.plan("one two three four".split(), (Cue(kind="breath", at=2),)), _tone, RATE)
    assert len(with_breath) / RATE > len(plain) / RATE + delivery.BREATH_SECONDS
    assert np.isfinite(with_breath).all() and np.abs(with_breath).max() <= 1.0


def test_whisper_is_quieter_noisy_and_finite_and_emphasis_never_clips():
    speech = _tone("a b c d e f g h", 1.0)
    whispered = delivery.whisper(speech, RATE)
    assert np.isfinite(whispered).all() and len(whispered) == len(speech)
    assert 0.2 < np.sqrt(np.mean(whispered ** 2)) / np.sqrt(np.mean(speech ** 2)) < 0.6
    loud = np.full(2000, .9, dtype=np.float32)
    assert np.abs(delivery.emphasize(loud)).max() <= .95


def test_breath_is_deterministic_and_quiet():
    first, second = delivery.breath(RATE), delivery.breath(RATE)
    assert np.array_equal(first, second) and abs(first).max() <= delivery.BREATH_PEAK + 1e-6


def test_profile_hash_is_stable_without_delivery_and_changes_with_it():
    base = dict(profile="off", lexicon={}, group_size=1, voice_processing="off")
    assert profile_hash(**base) == profile_hash(**base, delivery="off")
    assert profile_hash(**base) != profile_hash(**base, delivery="cues-v1")


class _FakeKokoro:
    calls: list = []

    def __init__(self, settings):
        self.settings = settings

    def synthesize(self, request):
        _FakeKokoro.calls.append((request.text, dict(request.settings).get("speed_scale")))
        path = request.output_path or None
        import tempfile
        target = path or tempfile.mktemp(suffix=".wav")
        sf.write(target, _tone(request.text, 1.0), RATE, subtype="PCM_16")
        return SimpleNamespace(artifact_path=target, provider_name="fake-kokoro")


def _topic(tmp_path, cues):
    scene = SimpleNamespace(scene_id="s1", vo="It was quiet and nobody noticed the failure until Friday.", cues=cues)
    return SimpleNamespace(scenes=[scene])


def _settings(delivery_mode):
    pacing = SimpleNamespace(voice_speed=1.15, spoken_profile="spoken-v1", pronunciation_lexicon={},
                             speech_group_size=1, voice_processing="off", max_pause_seconds=.15,
                             ffmpeg_executable="ffmpeg", delivery_cues=delivery_mode)
    kokoro = SimpleNamespace(model_copy=lambda update: SimpleNamespace(**update))
    return SimpleNamespace(pipeline=SimpleNamespace(reference_short=pacing, kokoro=kokoro,
                                                    piper=SimpleNamespace(voice_id="x")))


def test_cued_synthesis_uses_segments_and_records_a_manifest(tmp_path, monkeypatch):
    monkeypatch.setattr(prepare, "KokoroVoiceProvider", _FakeKokoro)
    monkeypatch.setattr(prepare, "PiperVoiceProvider", lambda settings: None)
    monkeypatch.setattr(prepare, "file_hash", lambda path: "h")
    cues = (Cue(kind="emphasis", at=2, end=3), Cue(kind="pause", at=5, seconds=0.5))
    _FakeKokoro.calls = []
    prepare.synthesize(_topic(tmp_path, cues), _settings("cues-v1"), tmp_path, "af_bella")
    manifest = json.loads((tmp_path / "voice-manifest.json").read_text())
    texts = [text for text, _ in _FakeKokoro.calls]
    assert texts == ["It was", "quiet", "and nobody", "noticed the failure until Friday."]
    assert dict(_FakeKokoro.calls)["quiet"] == "0.92"
    assert manifest["groups"][0]["spoken_text"] == "It was quiet and nobody noticed the failure until Friday."
    audio, _ = sf.read(tmp_path / manifest["groups"][0]["file"])
    plain_seconds = sum(len(t.split()) for t in texts) * 0.1
    assert len(audio) / RATE > plain_seconds + 0.45


def test_cues_are_ignored_when_delivery_is_off_or_scene_has_none(tmp_path, monkeypatch):
    monkeypatch.setattr(prepare, "KokoroVoiceProvider", _FakeKokoro)
    monkeypatch.setattr(prepare, "PiperVoiceProvider", lambda settings: None)
    monkeypatch.setattr(prepare, "file_hash", lambda path: "h")
    cues = (Cue(kind="pause", at=5, seconds=0.5),)
    _FakeKokoro.calls = []
    prepare.synthesize(_topic(tmp_path, cues), _settings("off"), tmp_path, "af_bella")
    prepare.synthesize(_topic(tmp_path, ()), _settings("cues-v1"), tmp_path, "af_bella")
    assert [text for text, _ in _FakeKokoro.calls] == ["It was quiet and nobody noticed the failure until Friday."] * 2


def test_a_video_keeps_at_most_two_whispers():
    narration = "[whisper]nobody was watching the logs[/whisper] and then it broke."
    scenes = [{"scene_id": f"s{i}", "template": "hook"} for i in range(4)]
    sections = [{"scene_id": f"s{i}", "narration": narration} for i in range(4)]
    bound = bind_reference_output({"reference_short": {"scenes": scenes}, "script_sections": sections},
                                  SimpleNamespace(sources=[], topic="t"))
    kinds = [[c["kind"] for c in s.get("cues", [])] for s in bound["reference_short"]["scenes"]]
    assert kinds == [["whisper"], ["whisper"], [], []]
    assert all(s["vo"] == "nobody was watching the logs and then it broke." for s in bound["reference_short"]["scenes"])
