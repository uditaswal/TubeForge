from __future__ import annotations

import io
import hashlib
import json
from pathlib import Path

import pytest

from tubeforge.core.config import FakeProviderConfig, MediaPipelineConfig
from tubeforge.domain.contracts import MediaSearchRequest
from tubeforge.providers.media.factory import create_media_provider
from tubeforge.providers.media.wikimedia import WikimediaCommonsProvider
from tubeforge.providers.media.local_graphics import PALETTE_ID, STYLE_VERSION
from tubeforge.pipeline.assets import validate_shorts_visual_manifest
from tubeforge.core.errors import ProviderValidationError


def _request(source: str) -> MediaSearchRequest:
    return MediaSearchRequest(scene_id="scene-1", queries=("engineer at workstation",), visual_type="illustration", required_license="licensed", visual_source=source)


def test_hybrid_media_provider_routes_generated_to_local_scene_art(tmp_path) -> None:
    provider = create_media_provider(MediaPipelineConfig(provider="hybrid"), FakeProviderConfig(artifact_root=tmp_path))
    candidate = provider.search(_request("generated"))[0]
    assert candidate.local_path and candidate.license_name == "CC0-1.0"
    assert candidate.source_version and candidate.source_version.startswith(f"{STYLE_VERSION}:{PALETTE_ID}:")
    assert (candidate.width, candidate.height) == (1920, 1080)
    assert candidate.provider_asset_id.startswith("local-storyboard-")
    assert provider.provider_name(_request("generated")) == "local-generated"


def test_hybrid_media_provider_has_a_local_cc0_fallback_for_empty_stock_results(tmp_path, monkeypatch) -> None:
    provider = create_media_provider(MediaPipelineConfig(provider="hybrid"), FakeProviderConfig(artifact_root=tmp_path))
    monkeypatch.setattr(provider.stock, "search", lambda _request: [])

    candidate = provider.search_local_fallback(_request("stock"))[0]

    assert candidate.local_path and candidate.license_name == "CC0-1.0"


def test_generated_shorts_art_is_full_hd_portrait_and_scene_specific(tmp_path) -> None:
    provider = create_media_provider(MediaPipelineConfig(provider="hybrid"), FakeProviderConfig(artifact_root=tmp_path))
    first_request = _request("generated").model_copy(update={"orientation": "portrait"})
    first = provider.search(first_request)[0]
    second = provider.search(first_request.model_copy(update={"scene_id": "scene-2", "queries": ("debugging boundary graph",)}))[0]

    assert (first.width, first.height) == (1080, 1920)
    assert first.local_path and second.local_path
    assert hashlib.sha256(Path(first.local_path).read_bytes()).digest() != hashlib.sha256(Path(second.local_path).read_bytes()).digest()
    assert first.provider_asset_id != second.provider_asset_id

    def entry(candidate, checksum: str) -> dict[str, object]:
        return {
            "candidate": candidate.model_dump(mode="json"),
            "validation": {"width": 1080, "height": 1920},
            "checksum_sha256": checksum,
        }

    manifest = {"scenes": {"scene-1": entry(first, "a" * 64), "scene-2": entry(second, "b" * 64)}}
    report = validate_shorts_visual_manifest(manifest)
    assert report["passed"] is True
    assert report["unique_scene_count"] == 2

    legacy = json.loads(json.dumps(manifest))
    for item in legacy["scenes"].values():
        item["candidate"]["source_version"] = item["candidate"]["source_version"].replace(STYLE_VERSION, "portrait-storyboard-v9")
    assert validate_shorts_visual_manifest(legacy)["passed"] is True

    manifest["scenes"]["scene-2"]["checksum_sha256"] = "a" * 64
    with pytest.raises(ProviderValidationError, match="distinct"):
        validate_shorts_visual_manifest(manifest)


def test_local_storyboard_frame_changes_with_scene_subject_and_display_text(tmp_path) -> None:
    provider = create_media_provider(MediaPipelineConfig(provider="hybrid"), FakeProviderConfig(artifact_root=tmp_path))
    base = _request("generated").model_copy(update={
        "orientation": "portrait", "visual_subject": "Inspect changed files",
        "visual_purpose": "Show what git status reports", "on_screen_text": "git status",
        "visual_elements": ("staged changes", "unstaged changes", "untracked files"),
        "queries": ("git status", "staged versus unstaged"),
    })
    first = provider.search(base)[0]
    second = provider.search(base.model_copy(update={"visual_subject": "Stage the chosen file", "on_screen_text": "git add path"}))[0]
    assert first.local_path and second.local_path
    assert Path(first.local_path).read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
    assert hashlib.sha256(Path(first.local_path).read_bytes()).digest() != hashlib.sha256(Path(second.local_path).read_bytes()).digest()
    labels_changed = provider.search(base.model_copy(update={"visual_elements": ("one selected file", "other edits")}))[0]
    assert labels_changed.provider_asset_id != first.provider_asset_id
    first_path = Path(first.local_path)
    first_path.write_bytes(b"corrupt cached source")
    recovered = provider.search(base)[0]
    assert recovered.local_path == first.local_path
    assert first_path.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")


def test_terminal_scene_shows_the_approved_command_and_rejects_unreadable_text(tmp_path) -> None:
    provider = create_media_provider(MediaPipelineConfig(provider="hybrid"), FakeProviderConfig(artifact_root=tmp_path))
    request = _request("generated").model_copy(update={
        "orientation": "portrait", "visual_type": "terminal",
        "visual_subject": "Inspect your container", "composition": "large terminal",
        "on_screen_text": "docker ps -a",
        "visual_elements": ("CONTAINER ID  STATUS", "demo  Exited (0)"),
    })
    candidate = provider.search(request)[0]
    assert candidate.local_path and Path(candidate.local_path).read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
    assert (candidate.width, candidate.height) == (1080, 1920)
    with pytest.raises(ProviderValidationError, match="too long to read"):
        provider.search(request.model_copy(update={"on_screen_text": "docker " + "very-long-argument " * 30}))



def test_wikimedia_stock_retains_only_no_attribution_public_domain_or_cc0(monkeypatch) -> None:
    payload = {"query": {"pages": {"1": {"pageid": 1, "canonicalurl": "https://commons.wikimedia.org/wiki/File:Scene.png", "imageinfo": [{"url": "https://upload.wikimedia.org/scene.png", "sha1": "abc", "mime": "image/png", "width": 1280, "height": 720, "extmetadata": {"LicenseShortName": {"value": "CC0 1.0"}, "LicenseUrl": {"value": "https://creativecommons.org/publicdomain/zero/1.0/"}, "Artist": {"value": "Creator"}}}]}, "2": {"pageid": 2, "imageinfo": [{"url": "https://upload.wikimedia.org/rejected.png", "mime": "image/png", "extmetadata": {"LicenseShortName": {"value": "CC BY-SA 4.0"}, "LicenseUrl": {"value": "https://creativecommons.org/licenses/by-sa/4.0/"}}}]}}}}

    class Response(io.StringIO):
        def __enter__(self): return self
        def __exit__(self, *_): self.close()

    monkeypatch.setattr("tubeforge.providers.media.wikimedia.urlopen", lambda *_args, **_kwargs: Response(json.dumps(payload)))
    provider = WikimediaCommonsProvider(MediaPipelineConfig(provider="wikimedia"))
    candidates = provider.search(_request("stock"))
    assert len(candidates) == 1
    assert candidates[0].license_name == "CC0-1.0"
    assert not candidates[0].attribution_required and not candidates[0].review_required


def test_portrait_stock_selection_rejects_landscape_or_soft_candidates() -> None:
    from datetime import UTC, datetime
    from tubeforge.domain.contracts import AssetCandidate
    from tubeforge.pipeline.assets import AssetLimits, select_candidate

    request = _request("stock").model_copy(update={"orientation": "portrait"})
    landscape = AssetCandidate(provider_asset_id="landscape", source_url="https://media.example.invalid/landscape.png", width=1920, height=1080, license_name="CC0-1.0", retrieved_at=datetime.now(UTC))
    limits = AssetLimits(frozenset({"media.example.invalid"}), frozenset({"CC0-1.0"}))
    with pytest.raises(ProviderValidationError, match="no permitted"):
        select_candidate([landscape], request, limits)
