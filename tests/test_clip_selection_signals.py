"""Chat-activity and loudness signals, and the default goal sent to the AI."""

import json
import shutil
import subprocess

import pytest

from tubeforge.clips import signals
from tubeforge.clips.engine import DEFAULT_GOAL, steering_text


def _chat_line(offset_ms: int, messages: int) -> str:
    return json.dumps({"replayChatItemAction": {"videoOffsetTimeMsec": str(offset_ms), "actions": [{"addChatItemAction": {}}] * messages}})


def test_parse_live_chat_counts_messages_per_bucket():
    lines = [_chat_line(1000, 2), _chat_line(29_000, 1), _chat_line(31_000, 5), "not json", _chat_line(-500, 3),
             json.dumps({"replayChatItemAction": {"videoOffsetTimeMsec": "95000", "actions": [{"other": {}}]}})]
    series = signals.parse_live_chat(lines)
    assert series["bucket"] == 30.0
    assert series["values"][:2] == [3, 5]
    assert series["messages"] == 8


def test_parse_live_chat_without_messages_is_empty():
    assert signals.parse_live_chat(["", "{}"]) == {}


def test_a_chat_spike_picks_its_window_and_names_the_reason():
    values = [10] * 120
    values[80] = 90  # one burst of chat at 2400 s
    found = signals.choose_windows(3600, {"chat": {"bucket": 30.0, "values": values}}, count=1)
    assert found and found[0].start <= 2415 <= found[0].end
    assert "chat" in found[0].reason


def test_constant_chat_does_not_mark_every_minute():
    assert signals._spikes(signals._rate_by_second({"bucket": 30.0, "values": [20] * 50}), 1500, 30.0) == {}


def test_loudness_adds_a_weaker_reason():
    values = [-30.0] * 100
    values[40] = -5.0
    found = signals.choose_windows(3000, {"audio_energy": {"bucket": 30.0, "values": values}}, count=1)
    assert "loud-audio" in found[0].reason and found[0].start <= 1215 <= found[0].end


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="needs ffmpeg")
def test_measure_audio_energy_sees_the_loud_half(tmp_path):
    quiet, loud, audio = tmp_path / "q.wav", tmp_path / "l.wav", tmp_path / "a.wav"
    for target, volume in ((quiet, 0.02), (loud, 0.8)):
        subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "sine=frequency=300:duration=60", "-af", f"volume={volume}", str(target)], check=True)
    listing = tmp_path / "list.txt"
    listing.write_text(f"file '{quiet}'\nfile '{loud}'\n")
    subprocess.run(["ffmpeg", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(listing), "-c", "copy", str(audio)], check=True)
    series = signals.measure_audio_energy(audio, tmp_path / "energy.json")
    values = series["values"]
    assert len(values) == 4 and values[0] < values[3] - 10
    assert signals.measure_audio_energy(audio, tmp_path / "energy.json") == series  # cached


def test_default_goal_is_always_sent_and_creator_text_follows():
    assert steering_text(None) == DEFAULT_GOAL
    assert steering_text("  focus on the funny bits ") == DEFAULT_GOAL + "\n\nThe creator also asks: focus on the funny bits"
    assert "whole" in DEFAULT_GOAL
