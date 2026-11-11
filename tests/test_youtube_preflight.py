"""YouTube Short eligibility is decided locally from actual media."""
from pathlib import Path
import subprocess

import pytest

from tubeforge.pipeline.youtube_preflight import YouTubePreflightError, check_youtube_short


def _video(path: Path, *, size: str = "90x160", video_codec: str = "libx264", audio_codec: str = "aac") -> Path:
    subprocess.run([
        "ffmpeg", "-v", "error", "-f", "lavfi", "-i", f"color=s={size}:d=1:r=5",
        "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono", "-t", "1", "-c:v", video_codec,
        "-c:a", audio_codec, "-y", str(path),
    ], check=True, timeout=20)
    return path


def test_short_preflight_accepts_actual_h264_aac_portrait(tmp_path: Path) -> None:
    check_youtube_short(_video(tmp_path / "valid.mp4"))


def test_short_preflight_rejects_size_ratio_and_codecs(tmp_path: Path) -> None:
    valid = _video(tmp_path / "valid.mp4")
    with pytest.raises(YouTubePreflightError, match="at most"):
        check_youtube_short(valid, max_bytes=valid.stat().st_size - 1)
    with pytest.raises(YouTubePreflightError, match="9:16"):
        check_youtube_short(_video(tmp_path / "wide.mp4", size="160x90"))
    with pytest.raises(YouTubePreflightError, match="H.264"):
        check_youtube_short(_video(tmp_path / "mpeg4.mp4", video_codec="mpeg4"))
    with pytest.raises(YouTubePreflightError, match="AAC"):
        check_youtube_short(_video(tmp_path / "mp3.mp4", audio_codec="libmp3lame"))


def test_short_preflight_fails_closed_on_missing_or_unprobeable_media(tmp_path: Path) -> None:
    with pytest.raises(YouTubePreflightError):
        check_youtube_short(tmp_path / "missing.mp4")
    invalid = tmp_path / "invalid.mp4"
    invalid.write_bytes(b"not video")
    with pytest.raises(YouTubePreflightError, match="could not be validated"):
        check_youtube_short(invalid)


def test_adapter_rejects_invalid_video_before_any_http(tmp_path: Path) -> None:
    import httpx
    from tubeforge.pipeline.delivery_executor import SafePreflightError
    from tubeforge.providers.publishing.account_youtube import AccountYouTubeAdapter

    video = tmp_path / "invalid.mp4"
    video.write_bytes(b"invalid media")
    calls = []
    client = httpx.Client(transport=httpx.MockTransport(lambda request: calls.append(request)))
    try:
        adapter = AccountYouTubeAdapter(client)
        with pytest.raises(SafePreflightError, match="could not be validated"):
            adapter.open_session(external_account_id="channel", credential={"token": "token"}, asset_path=video, metadata={"title": "Title", "caption": "Description", "contains_synthetic_media": False})
        assert calls == []
    finally:
        client.close()


def test_duration_limit_checks_180_second_boundary(tmp_path: Path, monkeypatch) -> None:
    import json
    from types import SimpleNamespace
    asset = tmp_path / 'video.mp4'
    asset.write_bytes(b'media')
    result = {'format': {'duration': '180'}, 'streams': [
        {'codec_type': 'video', 'codec_name': 'h264', 'width': 1080, 'height': 1920},
        {'codec_type': 'audio', 'codec_name': 'aac'},
    ]}
    monkeypatch.setattr('tubeforge.pipeline.youtube_preflight.subprocess.run', lambda *args, **kwargs: SimpleNamespace(stdout=json.dumps(result)))
    check_youtube_short(asset)
    result['format']['duration'] = '180.01'
    with pytest.raises(YouTubePreflightError, match='180 seconds'):
        check_youtube_short(asset)
