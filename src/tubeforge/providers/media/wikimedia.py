"""Opt-in Wikimedia Commons adapter using only the public MediaWiki API."""
from __future__ import annotations
import json
from datetime import UTC, datetime
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from tubeforge.core.config import MediaPipelineConfig
from tubeforge.core.errors import ProviderAuthenticationError, ProviderValidationError, RetryableProviderError
from tubeforge.domain.contracts import AssetCandidate, MediaSearchRequest

class WikimediaCommonsProvider:
    """Map Commons API results into rights-bearing provider-neutral candidates."""
    def __init__(self, config: MediaPipelineConfig) -> None: self.config = config
    def search(self, request: MediaSearchRequest) -> list[AssetCandidate]:
        query = " ".join(request.queries)
        params = urlencode({"action":"query","format":"json","generator":"search","gsrsearch":query,"gsrnamespace":"6","gsrlimit":"20","prop":"imageinfo","iiprop":"url|extmetadata|size|mime"})
        try:
            with urlopen(Request(f"{self.config.wikimedia_api_url}?{params}", headers={"User-Agent":"TubeForge/0.1"}), timeout=self.config.timeout_seconds) as response:
                payload=json.load(response)
        except TimeoutError as error: raise RetryableProviderError("Wikimedia search timed out") from error
        except OSError as error: raise RetryableProviderError("Wikimedia search unavailable") from error
        candidates=[]
        for page in payload.get("query",{}).get("pages",{}).values():
            info=(page.get("imageinfo") or [{}])[0]; metadata=info.get("extmetadata") or {}
            license_name=(metadata.get("LicenseShortName") or {}).get("value")
            license_url=(metadata.get("LicenseUrl") or {}).get("value")
            author=(metadata.get("Artist") or {}).get("value")
            url=info.get("url")
            if not (license_name and license_url and url): continue
            mime=str(info.get("mime", "")); media_type="video" if mime.startswith("video/") else "image"
            candidates.append(AssetCandidate(provider_asset_id=str(page["pageid"]), source_url=page.get("canonicalurl", url), download_url=url, source_version=str(info.get("sha1") or "" ) or None, media_type=media_type, width=info.get("width"), height=info.get("height"), author=author, license_name=license_name, license_url=license_url, attribution_text=author or None, attribution_required=True, review_required=True, retrieved_at=datetime.now(UTC)))
        return candidates
