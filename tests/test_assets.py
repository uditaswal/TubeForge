from __future__ import annotations

from datetime import UTC, datetime

import pytest

from tubeforge.core.errors import ProviderValidationError
from tubeforge.domain.contracts import AssetCandidate, MediaSearchRequest, ScenePlan
from tubeforge.pipeline.assets import AssetLimits, attribution_manifest, scene_request, select_candidate


def candidate(identifier: str, *, license_name: str = "CC0-1.0", width: int = 1920, height: int = 1080, review: bool = False) -> AssetCandidate:
    return AssetCandidate(provider_asset_id=identifier, source_url=f"https://media.example.invalid/{identifier}.jpg", download_url=f"https://media.example.invalid/{identifier}.jpg", license_name=license_name, width=width, height=height, review_required=review, retrieved_at=datetime.now(UTC))


def test_scene_mapping_selection_and_attribution_are_deterministic() -> None:
    scene = ScenePlan(scene_id="scene-1", visual_type="illustration", search_queries=("water cycle",), fallback_visual="text_card")
    request = scene_request(scene)
    selected = select_candidate([candidate("z", width=100), candidate("a")], request, AssetLimits(frozenset({"media.example.invalid"}), frozenset({"CC0-1.0"})))
    assert request.scene_id == scene.scene_id and selected.provider_asset_id == "a"
    assert attribution_manifest({scene.scene_id: selected})["assets"][0]["provider_asset_id"] == "a"


def test_rights_and_youtube_search_terms_fail_closed() -> None:
    with pytest.raises(ValueError, match="YouTube"):
        MediaSearchRequest(scene_id="scene-1", queries=("youtube.com creator",), visual_type="video", required_license="licensed")
    with pytest.raises(ProviderValidationError, match="permitted licensed"):
        select_candidate([candidate("bad", license_name="CC BY-NC 4.0")], MediaSearchRequest(scene_id="scene-1", queries=("rain",), visual_type="image", required_license="licensed"), AssetLimits(frozenset(), frozenset({"CC0-1.0"})))


def test_attribution_sensitive_asset_requires_text() -> None:
    with pytest.raises(ValueError, match="attribution-required"):
        AssetCandidate(provider_asset_id="a", source_url="https://media.example.invalid/a", license_name="CC BY 4.0", attribution_required=True, retrieved_at=datetime.now(UTC))
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tubeforge.core.config import DatabaseConfig
from tubeforge.db.models import Base
from tubeforge.db.repositories import AssetCacheRepository, AssetCacheReservation, CachedAsset
from tubeforge.db.session import create_database

def test_asset_cache_reservation_blocks_stale_acceptance_and_reuses(tmp_path: Path) -> None:
    db = create_database(DatabaseConfig(url=f"sqlite:///{tmp_path / 'cache.db'}"))
    Base.metadata.create_all(db.engine)
    repo = AssetCacheRepository(db.session_factory)
    now = datetime.now(UTC)
    first = repo.reserve_or_get("a" * 64, now=now, reservation_seconds=1)
    assert isinstance(first, AssetCacheReservation)
    assert repo.reserve_or_get("a" * 64, now=now, reservation_seconds=1) is None
    second = repo.reserve_or_get("a" * 64, now=now + timedelta(seconds=2), reservation_seconds=10)
    assert isinstance(second, AssetCacheReservation)
    cached = CachedAsset(str(tmp_path / "asset.png"), "b" * 64, {"validation_version": "m8-v1"})
    assert not repo.accept(first, cached, now=now)
    assert repo.accept(second, cached, now=now)
    assert isinstance(repo.reserve_or_get("a" * 64, now=now, reservation_seconds=1), CachedAsset)
    db.dispose()

def test_download_url_rejects_credentials_ports_and_traversal() -> None:
    from tubeforge.pipeline.assets import _validate_download_url
    limits = AssetLimits(frozenset({"media.example.invalid"}), frozenset({"CC0-1.0"}))
    for url in ("http://media.example.invalid/a.png", "https://user@media.example.invalid/a.png", "https://media.example.invalid:444/a.png", "https://media.example.invalid/%2e%2e/a.png"):
        with pytest.raises(ProviderValidationError): _validate_download_url(url, limits)

def test_png_validation_rejects_corrupt_and_excessive_dimensions(tmp_path: Path) -> None:
    from tubeforge.pipeline.assets import inspect_media
    limits = AssetLimits(frozenset(), frozenset({"CC0-1.0"}), max_width=10, max_height=10)
    corrupt = tmp_path / "bad.png"; corrupt.write_bytes(b"not image")
    with pytest.raises(ProviderValidationError): inspect_media(corrupt, "image", limits)
    huge = tmp_path / "huge.png"; huge.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\0\0\0\rIHDR" + (11).to_bytes(4,"big") + (11).to_bytes(4,"big"))
    with pytest.raises(ProviderValidationError): inspect_media(huge, "image", limits)

class _Chunks:
    def __init__(self, chunks: list[bytes], content_type: str = "image/png", length: str | None = None) -> None:
        from email.message import Message
        self.chunks, self.calls = chunks, 0
        self.headers = Message(); self.headers["Content-Type"] = content_type
        if length is not None: self.headers["Content-Length"] = length
    def read(self, _: int) -> bytes:
        self.calls += 1
        return self.chunks.pop(0) if self.chunks else b""

class _Opener:
    def __init__(self, response: object) -> None: self.response, self.calls = response, 0
    def open(self, request: object, timeout: int): self.calls += 1; return self.response

def test_network_download_streams_chunks_and_enforces_limits(tmp_path: Path) -> None:
    from tubeforge.pipeline.assets import AssetDownloader
    png = b"\x89PNG\r\n\x1a\n" + b"\0\0\0\rIHDR" + (1).to_bytes(4,"big") + (1).to_bytes(4,"big")
    response = _Chunks([png[:12], png[12:]])
    downloader = AssetDownloader(tmp_path / "cache", AssetLimits(frozenset({"media.example.invalid"}), frozenset({"CC0-1.0"})), _Opener(response))
    path, _, metadata = downloader.download("test", candidate("stream"))
    assert path.is_file() and response.calls >= 3 and metadata["media_type"] == "image"
    oversized = AssetDownloader(tmp_path / "other", AssetLimits(frozenset({"media.example.invalid"}), frozenset({"CC0-1.0"}), max_bytes=4), _Opener(_Chunks([png], length="1")))
    with pytest.raises(ProviderValidationError, match="byte limit"): oversized.download("test", candidate("large"))

def test_network_download_rejects_html_and_declared_oversize(tmp_path: Path) -> None:
    from tubeforge.pipeline.assets import AssetDownloader
    limits = AssetLimits(frozenset({"media.example.invalid"}), frozenset({"CC0-1.0"}), max_bytes=5)
    with pytest.raises(ProviderValidationError): AssetDownloader(tmp_path / "a", limits, _Opener(_Chunks([b"<html>"], "text/html"))).download("test", candidate("html"))
    with pytest.raises(ProviderValidationError, match="byte limit"): AssetDownloader(tmp_path / "b", limits, _Opener(_Chunks([], "image/png", "6"))).download("test", candidate("length"))

def test_asset_cache_reuse_rejects_missing_or_checksum_mismatched_file(tmp_path: Path) -> None:
    from tubeforge.pipeline.assets import AssetAcquisitionService, AssetDownloader
    db = create_database(DatabaseConfig(url=f"sqlite:///{tmp_path/'cachecheck.db'}")); Base.metadata.create_all(db.engine)
    repo = AssetCacheRepository(db.session_factory); limits = AssetLimits(frozenset({"media.example.invalid"}), frozenset({"CC0-1.0"}))
    downloader = AssetDownloader(tmp_path / "cache", limits, _Opener(_Chunks([])))
    key = downloader.cache_key("test", candidate("broken"))
    reservation = repo.reserve_or_get(key, now=datetime.now(UTC), reservation_seconds=30)
    assert isinstance(reservation, AssetCacheReservation)
    missing = tmp_path / "missing.png"
    assert repo.accept(reservation, CachedAsset(str(missing), "0" * 64, {"validation_version": "m8-v1"}), now=datetime.now(UTC))
    with pytest.raises(ProviderValidationError, match="response is empty"):
        AssetAcquisitionService(repo, downloader).acquire("test", candidate("broken"))
    db.dispose()

def test_download_follows_only_bounded_allowlisted_redirects(tmp_path: Path) -> None:
    from email.message import Message
    from urllib.error import HTTPError
    from tubeforge.pipeline.assets import AssetDownloader
    png = b"\x89PNG\r\n\x1a\n" + b"\0\0\0\rIHDR" + (1).to_bytes(4,"big") + (1).to_bytes(4,"big")
    headers = Message(); headers["Location"] = "https://media.example.invalid/final.png"
    redirect = HTTPError("https://media.example.invalid/start.png", 302, "found", headers, None)
    class Redirecting:
        def __init__(self): self.calls = 0
        def open(self, request, timeout):
            self.calls += 1
            if self.calls == 1: raise redirect
            return _Chunks([png])
    limits=AssetLimits(frozenset({"media.example.invalid"}), frozenset({"CC0-1.0"}), max_redirects=1)
    opener=Redirecting(); path, _, _ = AssetDownloader(tmp_path/"cache", limits, opener).download("test", candidate("redirect"))
    assert path.is_file() and opener.calls == 2
    with pytest.raises(ProviderValidationError, match="redirect"):
        AssetDownloader(tmp_path/"blocked", AssetLimits(frozenset({"media.example.invalid"}), frozenset({"CC0-1.0"}), max_redirects=0), Redirecting()).download("test", candidate("blocked"))

def test_video_inspection_uses_safe_argument_array_and_validates_stream(monkeypatch, tmp_path: Path) -> None:
    from types import SimpleNamespace
    from tubeforge.pipeline.assets import inspect_media
    movie = tmp_path / "tiny.mp4"; movie.write_bytes(b"fake")
    calls = []
    def run(command, **kwargs):
        calls.append((command, kwargs))
        return SimpleNamespace(returncode=0, stdout=b'{"format":{"duration":"2.0","format_name":"mov"},"streams":[{"codec_type":"video","codec_name":"h264","width":16,"height":9}]}', stderr=b"")
    monkeypatch.setattr("tubeforge.pipeline.assets.subprocess.run", run)
    data = inspect_media(movie, "video", AssetLimits(frozenset(), frozenset(), max_width=20, max_height=20, max_duration_seconds=5))
    assert data["codec"] == "h264" and calls[0][1]["shell"] is False and isinstance(calls[0][0], list)

def test_video_inspection_rejects_missing_stream_and_timeout(monkeypatch, tmp_path: Path) -> None:
    import subprocess
    from types import SimpleNamespace
    from tubeforge.core.errors import RetryableProviderError
    from tubeforge.pipeline.assets import inspect_media
    movie = tmp_path / "tiny.mp4"; movie.write_bytes(b"fake")
    monkeypatch.setattr("tubeforge.pipeline.assets.subprocess.run", lambda *a, **k: SimpleNamespace(returncode=0, stdout=b'{"format":{"duration":"1"},"streams":[]}', stderr=b""))
    with pytest.raises(ProviderValidationError, match="usable video"): inspect_media(movie, "video", AssetLimits(frozenset(), frozenset()))
    def timeout(*a, **k): raise subprocess.TimeoutExpired("ffprobe", 30)
    monkeypatch.setattr("tubeforge.pipeline.assets.subprocess.run", timeout)
    with pytest.raises(RetryableProviderError, match="timed out"): inspect_media(movie, "video", AssetLimits(frozenset(), frozenset()))

def test_rights_sensitive_candidates_require_manual_review() -> None:
    request = MediaSearchRequest(scene_id="scene-1", queries=("rain",), visual_type="image", required_license="licensed")
    limits = AssetLimits(frozenset(), frozenset({"CC0-1.0"}))
    with pytest.raises(ProviderValidationError, match="permitted licensed"):
        select_candidate([candidate("review", review=True)], request, limits)
    sensitive = AssetCandidate(provider_asset_id="credit", source_url="https://media.example.invalid/credit.png", license_name="CC0-1.0", attribution_required=True, attribution_text="Credit", retrieved_at=datetime.now(UTC))
    with pytest.raises(ProviderValidationError, match="permitted licensed"):
        select_candidate([sensitive], request, limits)

def test_cache_identity_changes_without_persisting_url_query_secrets(tmp_path: Path) -> None:
    from tubeforge.pipeline.assets import AssetDownloader
    downloader=AssetDownloader(tmp_path, AssetLimits(frozenset({"media.example.invalid"}), frozenset({"CC0-1.0"})))
    base=candidate("identity")
    signed=AssetCandidate(provider_asset_id="identity", source_url="https://media.example.invalid/identity.jpg?signature=secret", download_url="https://media.example.invalid/identity.jpg?signature=secret", license_name="CC0-1.0", retrieved_at=datetime.now(UTC))
    video=AssetCandidate(provider_asset_id="identity", source_url="https://media.example.invalid/identity.jpg", download_url="https://media.example.invalid/identity.jpg", license_name="CC0-1.0", media_type="video", retrieved_at=datetime.now(UTC))
    assert downloader.cache_key("provider", base) == downloader.cache_key("provider", signed)
    assert downloader.cache_key("provider", base) != downloader.cache_key("provider", video)

def test_attribution_manifest_deduplicates_asset_and_retains_scene_ids() -> None:
    asset = candidate("shared")
    manifest = attribution_manifest({"scene-b": asset, "scene-a": asset})
    assert len(manifest["assets"]) == 1
    assert manifest["assets"][0]["scene_ids"] == ["scene-a", "scene-b"]

def test_downloader_cancellation_removes_only_partial_file(tmp_path: Path) -> None:
    from tubeforge.pipeline.assets import AssetAcquisitionCancelled, AssetDownloader
    png = b"\x89PNG\r\n\x1a\n" + b"\0\0\0\rIHDR" + (1).to_bytes(4,"big") + (1).to_bytes(4,"big")
    response = _Chunks([png[:12], png[12:]])
    calls = [0]
    def cancelled() -> bool:
        calls[0] += 1
        return calls[0] > 1
    downloader = AssetDownloader(tmp_path / "cache", AssetLimits(frozenset({"media.example.invalid"}), frozenset({"CC0-1.0"})), _Opener(response))
    with pytest.raises(AssetAcquisitionCancelled): downloader.download("test", candidate("cancel-stream"), cancelled)
    assert not list((tmp_path / "cache").rglob("*.part"))

def test_png_validation_enforces_minimum_and_pixel_limits(tmp_path: Path) -> None:
    from tubeforge.pipeline.assets import inspect_media
    png = b"\x89PNG\r\n\x1a\n" + b"\0\0\0\rIHDR" + (2).to_bytes(4,"big") + (2).to_bytes(4,"big")
    path = tmp_path / "tiny.png"; path.write_bytes(png)
    with pytest.raises(ProviderValidationError): inspect_media(path, "image", AssetLimits(frozenset(), frozenset(), min_width=3, min_height=3))
    with pytest.raises(ProviderValidationError): inspect_media(path, "image", AssetLimits(frozenset(), frozenset(), max_pixels=3))

def test_http_auth_and_transient_failures_are_classified(tmp_path: Path) -> None:
    from email.message import Message
    from urllib.error import HTTPError
    from tubeforge.core.errors import ProviderAuthenticationError, RetryableProviderError
    from tubeforge.pipeline.assets import AssetDownloader
    class Failing:
        def __init__(self, code: int): self.code = code
        def open(self, request, timeout): raise HTTPError(request.full_url, self.code, "failure", Message(), None)
    limits = AssetLimits(frozenset({"media.example.invalid"}), frozenset({"CC0-1.0"}))
    with pytest.raises(ProviderAuthenticationError): AssetDownloader(tmp_path / "auth", limits, Failing(401)).download("test", candidate("auth"))
    with pytest.raises(RetryableProviderError): AssetDownloader(tmp_path / "retry", limits, Failing(503)).download("test", candidate("retry"))

def test_shared_asset_cache_reuse_avoids_second_download(tmp_path: Path) -> None:
    from tubeforge.pipeline.assets import AssetAcquisitionService, AssetDownloader
    png = b"\x89PNG\r\n\x1a\n" + b"\0\0\0\rIHDR" + (1).to_bytes(4,"big") + (1).to_bytes(4,"big")
    source = tmp_path / "source.png"; source.write_bytes(png)
    asset = AssetCandidate(provider_asset_id="shared", source_url="https://media.example.invalid/shared.png", download_url="https://media.example.invalid/shared.png", local_path=str(source), license_name="CC0-1.0", retrieved_at=datetime.now(UTC))
    db = create_database(DatabaseConfig(url=f"sqlite:///{tmp_path/'shared.db'}")); Base.metadata.create_all(db.engine)
    service = AssetAcquisitionService(AssetCacheRepository(db.session_factory), AssetDownloader(tmp_path / "cache", AssetLimits(frozenset({"media.example.invalid"}), frozenset({"CC0-1.0"}))))
    one = service.acquire("fake", asset)
    source.unlink()
    two = service.acquire("fake", asset)
    assert one[0] == two[0] and two[0].is_file()
    db.dispose()

def test_asset_limits_use_validated_media_configuration() -> None:
    from tubeforge.core.config import MediaPipelineConfig
    from tubeforge.pipeline.assets import asset_limits_from_config
    limits = asset_limits_from_config(MediaPipelineConfig(max_bytes=2048, max_redirects=2, allowed_hosts=("assets.example",), allowed_licenses=("CC0-1.0",)))
    assert limits.max_bytes == 2048 and limits.max_redirects == 2 and limits.allowed_hosts == frozenset({"assets.example"})
