from __future__ import annotations

import io
import json

from tubeforge.core.config import FakeProviderConfig, MediaPipelineConfig
from tubeforge.domain.contracts import MediaSearchRequest
from tubeforge.providers.media.factory import create_media_provider
from tubeforge.providers.media.wikimedia import WikimediaCommonsProvider


def _request(source: str) -> MediaSearchRequest:
    return MediaSearchRequest(scene_id="scene-1", queries=("engineer at workstation",), visual_type="illustration", required_license="licensed", visual_source=source)


def test_hybrid_media_provider_routes_generated_to_local_scene_art(tmp_path) -> None:
    provider = create_media_provider(MediaPipelineConfig(provider="hybrid"), FakeProviderConfig(artifact_root=tmp_path))
    candidate = provider.search(_request("generated"))[0]
    assert candidate.local_path and candidate.license_name == "CC0-1.0"
    assert provider.provider_name(_request("generated")) == "local-generated"


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
