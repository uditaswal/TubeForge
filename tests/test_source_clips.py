from __future__ import annotations

import wave
from pathlib import Path
import subprocess

import pytest

from tubeforge.clipping.analysis import analyze_wav
from tubeforge.clipping.source import YtDlpSourceProvider, validate_source_url
from tubeforge.core.errors import ProviderValidationError
from tubeforge.core.state_machine import PipelineSnapshot, PipelineStateMachine
from tubeforge.domain.states import JobState


def test_source_url_rejects_non_public_and_credentialed_targets() -> None:
    assert validate_source_url("https://www.youtube.com/watch?v=abc") == "https://www.youtube.com/watch?v=abc"
    for value in ("file:///etc/passwd", "http://127.0.0.1/video", "http://localhost/video", "https://user:secret@example.com/video"):
        with pytest.raises(ProviderValidationError):
            validate_source_url(value)


def test_ytdlp_inspection_and_acquisition_are_argument_safe(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    commands: list[list[str]] = []
    def fake_run(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        commands.append(command)
        if "--dump-single-json" in command:
            return subprocess.CompletedProcess(command, 0, '{"id":"abc","title":"Demo","uploader":"Creator","duration":42}', "")
        destination = Path(command[command.index("--paths") + 1]); destination.mkdir(parents=True, exist_ok=True)
        (destination / "source.mp4").write_bytes(b"media")
        return subprocess.CompletedProcess(command, 0, "", "")
    monkeypatch.setattr("tubeforge.clipping.source.subprocess.run", fake_run)
    provider = YtDlpSourceProvider("yt-dlp")
    metadata = provider.inspect("https://example.com/watch?v=abc")
    path = provider.acquire("https://example.com/watch?v=abc", tmp_path, captions=True)
    assert metadata["id"] == "abc" and metadata["duration_seconds"] == 42.0
    assert path.name == "source.mp4" and provider.can_handle("https://example.com/watch?v=abc")
    assert "--no-playlist" in commands[0] and "--write-auto-subs" in commands[1]
    assert commands[0][commands[0].index("--socket-timeout") + 1] == "900"
    assert all(";" not in item for command in commands for item in command)


def test_source_branch_is_durable_and_does_not_skip_final_ready() -> None:
    machine = PipelineStateMachine()
    snapshot = PipelineSnapshot(JobState.TOPIC_CREATED)
    for state in (JobState.SOURCE_INSPECTING, JobState.SOURCE_ACQUIRING, JobState.SOURCE_ANALYZING, JobState.CLIP_RENDERING, JobState.FINAL_READY):
        snapshot = machine.transition(snapshot, state)
    assert snapshot.state is JobState.FINAL_READY


def test_audio_highlights_are_non_overlapping_and_repeatable(tmp_path: Path) -> None:
    path = tmp_path / "energy.wav"
    with wave.open(str(path), "wb") as output:
        output.setnchannels(1); output.setsampwidth(2); output.setframerate(100)
        output.writeframes(b"\x00\x00" * 200 + b"\xff\x7f" * 100 + b"\x00\x00" * 200 + b"\xff\x7f" * 100)
    first = analyze_wav(path, window_seconds=.5, duration_seconds=6, min_duration=1, max_duration=2, padding=0, count=2)
    second = analyze_wav(path, window_seconds=.5, duration_seconds=6, min_duration=1, max_duration=2, padding=0, count=2)
    assert first == second and first
    assert all(left.end_seconds <= right.start_seconds or right.end_seconds <= left.start_seconds for left, right in zip(first, first[1:]))
