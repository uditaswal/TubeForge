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


def test_the_lookup_passes_a_javascript_runtime_and_the_cookies_file_when_they_exist(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    commands: list[list[str]] = []
    def fake_run(command, **_kwargs):
        commands.append(command)
        return subprocess.CompletedProcess(command, 0, '{"id":"abc","title":"Demo","duration":42}', "")
    monkeypatch.setattr("tubeforge.clipping.source.subprocess.run", fake_run)
    monkeypatch.setattr("tubeforge.clipping.source.shutil.which", lambda name: "/usr/bin/node" if name == "node" else None)
    cookies = tmp_path / "youtube-cookies.txt"
    YtDlpSourceProvider("yt-dlp", cookies_file=cookies).inspect("https://example.com/watch?v=abc")
    assert "--js-runtimes" in commands[0] and "node" in commands[0] and "--cookies" not in commands[0]  # no cookies yet
    cookies.write_text("# Netscape HTTP Cookie File\n")
    YtDlpSourceProvider("yt-dlp", cookies_file=cookies).inspect("https://example.com/watch?v=abc")
    assert commands[1][commands[1].index("--cookies") + 1] == str(cookies)


@pytest.mark.parametrize("have_cookies", [False, True])
def test_a_bot_check_says_what_to_do_instead_of_dumping_the_tool_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, have_cookies: bool) -> None:
    def fake_run(command, **_kwargs):
        return subprocess.CompletedProcess(command, 1, "", "ERROR: [youtube] abc: Sign in to confirm you’re not a bot. Use --cookies-from-browser or --cookies for the authentication.")
    monkeypatch.setattr("tubeforge.clipping.source.subprocess.run", fake_run)
    cookies = tmp_path / "youtube-cookies.txt"
    if have_cookies:
        cookies.write_text("x")
    with pytest.raises(ProviderValidationError) as error:
        YtDlpSourceProvider("yt-dlp", cookies_file=cookies).inspect("https://example.com/watch?v=abc")
    message = str(error.value)
    assert "youtube-cookies.txt" in message or "expired" in message
    assert "--cookies-from-browser" not in message and ("export them again" in message) is have_cookies


def test_the_cookie_option_is_added_only_when_the_file_exists(tmp_path: Path) -> None:
    from types import SimpleNamespace
    from tubeforge.clips.ytdlp_options import cookie_options, is_bot_check
    path = tmp_path / "c.txt"
    assert cookie_options(SimpleNamespace(youtube_cookies_file=str(path))) == {}
    path.write_text("x")
    assert cookie_options(SimpleNamespace(youtube_cookies_file=str(path))) == {"cookiefile": str(path)}
    assert is_bot_check("ERROR: Sign in to confirm you’re not a bot.") and not is_bot_check("HTTP 503")
