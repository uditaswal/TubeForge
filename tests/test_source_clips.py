from __future__ import annotations

from pathlib import Path
import subprocess

import pytest

from tubeforge.clipping.source import YtDlpSourceProvider, validate_source_url
from tubeforge.core.errors import ProviderValidationError
from tubeforge.core.state_machine import PipelineSnapshot, PipelineStateMachine
from tubeforge.domain.states import JobState


def test_source_url_rejects_non_public_and_credentialed_targets() -> None:
    assert validate_source_url("https://www.youtube.com/watch?v=abc") == "https://www.youtube.com/watch?v=abc"
    for value in ("file:///etc/passwd", "http://127.0.0.1/video", "http://localhost/video", "https://user:secret@example.com/video"):
        with pytest.raises(ProviderValidationError):
            validate_source_url(value)


def test_ytdlp_inspection_is_argument_safe(monkeypatch: pytest.MonkeyPatch) -> None:
    commands: list[list[str]] = []
    def fake_run(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        commands.append(command)
        return subprocess.CompletedProcess(command, 0, '{"id":"abc","title":"Demo","uploader":"Creator","duration":42}', "")
    monkeypatch.setattr("tubeforge.clipping.source.subprocess.run", fake_run)
    provider = YtDlpSourceProvider("yt-dlp")
    metadata = provider.inspect("https://example.com/watch?v=abc")
    assert metadata["id"] == "abc" and metadata["duration_seconds"] == 42.0 and provider.can_handle("https://example.com/watch?v=abc")
    assert "--no-playlist" in commands[0]
    assert commands[0][commands[0].index("--socket-timeout") + 1] == "900"
    assert all(";" not in item for command in commands for item in command)


def test_source_branch_is_durable_and_does_not_skip_final_ready() -> None:
    machine = PipelineStateMachine()
    snapshot = PipelineSnapshot(JobState.TOPIC_CREATED)
    for state in (JobState.SOURCE_INSPECTING, JobState.SOURCE_ACQUIRING, JobState.SOURCE_ANALYZING, JobState.CLIP_RENDERING, JobState.FINAL_READY):
        snapshot = machine.transition(snapshot, state)
    assert snapshot.state is JobState.FINAL_READY
