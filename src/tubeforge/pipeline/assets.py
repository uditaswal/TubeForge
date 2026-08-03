"""M8 provider-neutral licensed asset selection, streaming, and checkpoints."""

from __future__ import annotations

import hashlib
import json
import mimetypes
import os
import tempfile
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import unquote, urljoin, urlparse
from urllib.request import Request, build_opener, HTTPRedirectHandler

from tubeforge.core.config import MediaPipelineConfig
from tubeforge.core.errors import ProviderAuthenticationError, ProviderValidationError, RetryableProviderError
from tubeforge.domain.contracts import AssetCandidate, MediaSearchRequest, ScenePlan
from tubeforge.domain.providers import MediaProvider
from tubeforge.db.repositories import AssetCacheRepository, AssetCacheReservation, CachedAsset


@dataclass(frozen=True, slots=True)
class AssetLimits:
    allowed_hosts: frozenset[str]
    allowed_licenses: frozenset[str]
    max_bytes: int = 100_000_000
    timeout_seconds: int = 30
    max_redirects: int = 0
    max_width: int = 12_000
    max_height: int = 12_000
    min_width: int = 1
    min_height: int = 1
    max_pixels: int = 100_000_000
    max_duration_seconds: float = 900.0
    allowed_media_types: frozenset[str] = frozenset({"image", "video"})


def asset_limits_from_config(config: MediaPipelineConfig) -> AssetLimits:
    """Translate validated configuration without leaking it into providers."""
    return AssetLimits(frozenset(config.allowed_hosts), frozenset(config.allowed_licenses), config.max_bytes, config.timeout_seconds, config.max_redirects, config.max_width, config.max_height, config.min_width, config.min_height, config.max_width * config.max_height, config.max_duration_seconds, frozenset(config.allowed_media_types))
def scene_request(scene: ScenePlan) -> MediaSearchRequest:
    """Turn approved scene-plan fields into a deterministic search request."""
    orientation = "portrait" if scene.visual_type in {"portrait", "vertical"} else "landscape"
    return MediaSearchRequest(scene_id=scene.scene_id, queries=tuple(" ".join(query.split()) for query in scene.search_queries), visual_type=scene.visual_type, required_license="licensed", orientation=orientation)

def select_candidate(candidates: list[AssetCandidate], request: MediaSearchRequest, limits: AssetLimits) -> AssetCandidate:
    eligible = [candidate for candidate in candidates if candidate.media_type in limits.allowed_media_types and candidate.license_name.casefold() in {value.casefold() for value in limits.allowed_licenses} and not candidate.editorial_only and not candidate.review_required and not candidate.attribution_required]
    if not eligible:
        raise ProviderValidationError(f"no permitted licensed asset for scene {request.scene_id}")
    def rank(candidate: AssetCandidate) -> tuple[int, int, int, str]:
        orientation = 0
        if candidate.width and candidate.height and request.orientation != "any":
            actual = "landscape" if candidate.width >= candidate.height else "portrait"
            orientation = 0 if actual == request.orientation else 1
        review = int(candidate.review_required or candidate.attribution_required)
        pixels = -(candidate.width or 0) * (candidate.height or 0)
        return review, orientation, pixels, candidate.provider_asset_id
    return sorted(eligible, key=rank)[0]

class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        return None

class AssetAcquisitionCancelled(RuntimeError):
    """Cooperative cancellation before accepting an asset checkpoint."""

class AssetDownloader:
    """Streams one allowlisted binary to a temporary path, never executing it."""
    validation_version = "m8-v1"
    def __init__(self, cache_root: Path, limits: AssetLimits, opener: object | None = None) -> None:
        self.cache_root, self.limits = cache_root, limits
        self._opener = opener or build_opener(_NoRedirect)

    def cache_key(self, provider: str, candidate: AssetCandidate) -> str:
        raw_url = str(candidate.download_url or candidate.source_url)
        parsed = urlparse(raw_url)
        normalized_url = f"{parsed.scheme.lower()}://{parsed.netloc.casefold()}{parsed.path}"
        value = {"provider": provider, "asset": candidate.provider_asset_id, "version": candidate.source_version, "url": normalized_url, "media_type": candidate.media_type, "validation": self.validation_version}
        return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()

    def _copy_local(self, provider: str, candidate: AssetCandidate, cancellation_requested: Callable[[], bool] | None = None) -> tuple[Path, str, dict[str, object]]:
        source=Path(str(candidate.local_path)); key=self.cache_key(provider,candidate); target=self.cache_root/key[:2]/f"{key}.png"
        if not source.is_file() or source.stat().st_size == 0: raise ProviderValidationError("offline fake media is missing")
        target.parent.mkdir(parents=True,exist_ok=True); fd, temporary_name = tempfile.mkstemp(prefix="asset-", suffix=".part", dir=target.parent); os.close(fd); temporary=Path(temporary_name)
        try:
            total=0
            with source.open("rb") as incoming, temporary.open("wb") as outgoing:
                while chunk:=incoming.read(64*1024):
                    if cancellation_requested and cancellation_requested(): raise AssetAcquisitionCancelled("cancelled during asset download")
                    total+=len(chunk)
                    if total > self.limits.max_bytes: raise ProviderValidationError("asset exceeds configured byte limit")
                    outgoing.write(chunk)
            temporary.replace(target); metadata={"checksum_sha256":_checksum(target),"bytes":total,"content_type":"image/png","validation_version":self.validation_version,"cached_at":datetime.now(UTC).isoformat(),**inspect_media(target,candidate.media_type,self.limits)}; _atomic_json(target.with_suffix(".json"),metadata); return target,key,metadata
        except Exception:
            temporary.unlink(missing_ok=True); raise
    def download(self, provider: str, candidate: AssetCandidate, cancellation_requested: Callable[[], bool] | None = None) -> tuple[Path, str, dict[str, object]]:
        if cancellation_requested and cancellation_requested(): raise AssetAcquisitionCancelled("cancelled before asset download")
        url = str(candidate.download_url or candidate.source_url)
        _validate_download_url(url, self.limits)
        if candidate.license_name.casefold() not in {item.casefold() for item in self.limits.allowed_licenses}:
            raise ProviderValidationError("asset licence is not permitted by configuration")
        if candidate.local_path:
            return self._copy_local(provider, candidate, cancellation_requested)
        key = self.cache_key(provider, candidate); target = self.cache_root / key[:2] / key
        metadata_path = target.with_suffix(".json")
        if target.is_file() and metadata_path.is_file():
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            if metadata.get("checksum_sha256") == _checksum(target) and metadata.get("validation_version") == self.validation_version:
                return target, key, metadata
        target.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary_name = tempfile.mkstemp(prefix="asset-", suffix=".part", dir=target.parent); os.close(fd); temporary=Path(temporary_name)
        try:
            response = None
            for redirect_count in range(self.limits.max_redirects + 1):
                request = Request(url, headers={"User-Agent": "TubeForge/0.1", "Accept": "image/*,video/*"})
                try:
                    response = self._opener.open(request, timeout=self.limits.timeout_seconds)
                    break
                except HTTPError as error:
                    if 300 <= error.code < 400:
                        location = error.headers.get("Location") if error.headers else None
                        if not location or redirect_count >= self.limits.max_redirects:
                            raise ProviderValidationError("asset redirect limit exceeded") from error
                        url = urljoin(url, location)
                        _validate_download_url(url, self.limits)
                        continue
                    if error.code in {401, 403, 429}:
                        raise ProviderAuthenticationError("asset provider credentials or quota require attention") from error
                    if error.code >= 500:
                        raise RetryableProviderError("asset provider temporarily unavailable") from error
                    raise ProviderValidationError("asset download was rejected") from error
                except (URLError, TimeoutError) as error:
                    raise RetryableProviderError("asset download failed") from error
            if response is None:
                raise RetryableProviderError("asset download did not return a response")
            content_length = response.headers.get("Content-Length")
            if content_length and int(content_length) > self.limits.max_bytes:
                raise ProviderValidationError("asset exceeds configured byte limit")
            content_type = response.headers.get_content_type()
            if not content_type.startswith(("image/", "video/")):
                raise ProviderValidationError("asset response is not image or video media")
            total = 0
            with temporary.open("wb") as stream:
                while chunk := response.read(64 * 1024):
                    if cancellation_requested and cancellation_requested(): raise AssetAcquisitionCancelled("cancelled during asset download")
                    total += len(chunk)
                    if total > self.limits.max_bytes: raise ProviderValidationError("asset exceeds configured byte limit")
                    stream.write(chunk)
            if total == 0: raise ProviderValidationError("asset response is empty")
            extension = mimetypes.guess_extension(content_type) or ".bin"
            final = target.with_suffix(extension)
            temporary.replace(final)
            metadata = {"checksum_sha256": _checksum(final), "bytes": total, "content_type": content_type, "validation_version": self.validation_version, "cached_at": datetime.now(UTC).isoformat(), **inspect_media(final, candidate.media_type, self.limits)}
            _atomic_json(metadata_path, metadata)
            return final, key, metadata
        except Exception:
            temporary.unlink(missing_ok=True)
            raise

def attribution_manifest(selected: dict[str, AssetCandidate]) -> dict[str, object]:
    """Produce a stable, deduplicated manifest only from accepted scene mappings."""
    grouped: dict[tuple[str, str], tuple[AssetCandidate, list[str]]] = {}
    for scene_id, asset in sorted(selected.items()):
        key = (asset.provider_asset_id, str(asset.source_url))
        if key not in grouped: grouped[key] = (asset, [])
        grouped[key][1].append(scene_id)
    assets = []
    for (_, _), (asset, scene_ids) in sorted(grouped.items()):
        assets.append({"scene_ids": scene_ids, "provider_asset_id": asset.provider_asset_id, "source_url": str(asset.source_url), "author": asset.author, "license_name": asset.license_name, "license_url": str(asset.license_url) if asset.license_url else None, "retrieved_at": asset.retrieved_at.isoformat(), "attribution_required": asset.attribution_required, "attribution_text": asset.attribution_text, "review_required": asset.review_required})
    return {"assets": assets}
def _checksum(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024): digest.update(chunk)
    return digest.hexdigest()

def _atomic_json(path: Path, value: dict[str, object]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp"); temporary.write_text(json.dumps(value, sort_keys=True), encoding="utf-8"); os.replace(temporary, path)

def inspect_media(path: Path, expected_type: str, limits: AssetLimits, *, ffprobe: str = "ffprobe") -> dict[str, object]:
    """Validate a completed file using bounded, argument-array inspection."""
    if not path.is_file() or path.stat().st_size == 0: raise ProviderValidationError("asset is missing or empty")
    if expected_type == "image":
        with path.open("rb") as stream: header=stream.read(32)
        if header.startswith(b"\x89PNG\r\n\x1a\n") and len(header) >= 24:
            width=int.from_bytes(header[16:20],"big"); height=int.from_bytes(header[20:24],"big"); container="png"
        elif header.startswith(b"\xff\xd8"):
            # JPEG dimensions require marker parsing; ffprobe remains the safe inspector.
            width=height=0; container="jpeg"
        else: raise ProviderValidationError("image signature is unsupported or corrupt")
        if width and (width < limits.min_width or height < limits.min_height or width > limits.max_width or height > limits.max_height or width * height > limits.max_pixels): raise ProviderValidationError("image dimensions exceed configured limits")
        return {"media_type":"image","container":container,"width":width,"height":height,"duration_seconds":None}
    command=[ffprobe,"-v","error","-show_entries","format=format_name,duration:stream=codec_type,codec_name,width,height","-of","json",str(path)]
    try: result=subprocess.run(command,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=30,check=False,shell=False)
    except subprocess.TimeoutExpired as error: raise RetryableProviderError("ffprobe timed out") from error
    except OSError as error: raise ProviderValidationError("ffprobe executable unavailable") from error
    if result.returncode: raise ProviderValidationError("ffprobe rejected media")
    try:
        data=json.loads(result.stdout.decode("utf-8")); streams=data.get("streams",[]); stream=next(item for item in streams if item.get("codec_type")=="video"); duration=float(data["format"]["duration"])
        width=int(stream["width"]); height=int(stream["height"])
    except (ValueError, KeyError, StopIteration, TypeError, json.JSONDecodeError) as error: raise ProviderValidationError("media lacks a usable video stream") from error
    if width > limits.max_width or height > limits.max_height or duration <= 0 or duration > limits.max_duration_seconds: raise ProviderValidationError("media dimensions or duration are invalid")
    return {"media_type":"video","container":str(data["format"].get("format_name","")),"width":width,"height":height,"duration_seconds":duration,"codec":str(stream.get("codec_name",""))}
class AssetAcquisitionService:
    """Coordinates cache ownership around all slow download and validation work."""
    def __init__(self, cache: AssetCacheRepository, downloader: AssetDownloader, *, reservation_seconds: int = 300) -> None:
        self.cache, self.downloader, self.reservation_seconds = cache, downloader, reservation_seconds
    def acquire(self, provider: str, candidate: AssetCandidate, cancellation_requested: Callable[[], bool] | None = None) -> tuple[Path, str, dict[str, object]]:
        if cancellation_requested and cancellation_requested(): raise AssetAcquisitionCancelled("cancelled before asset reservation")
        key=self.downloader.cache_key(provider,candidate); claimed=self.cache.reserve_or_get(key,now=datetime.now(UTC),reservation_seconds=self.reservation_seconds)
        if isinstance(claimed,CachedAsset):
            path=Path(claimed.path)
            if path.is_file() and path.stat().st_size and _checksum(path)==claimed.checksum_sha256 and claimed.metadata.get("validation_version")==self.downloader.validation_version:
                return path,key,claimed.metadata
            self.cache.invalidate(key, now=datetime.now(UTC))
            return self.acquire(provider, candidate, cancellation_requested)
        if claimed is None: raise RetryableProviderError("asset cache acquisition is owned by another worker")
        path, downloaded_key, metadata=self.downloader.download(provider,candidate,cancellation_requested)
        if cancellation_requested and cancellation_requested(): raise AssetAcquisitionCancelled("cancelled before cache acceptance")
        accepted=self.cache.accept(claimed,CachedAsset(str(path),str(metadata["checksum_sha256"]),metadata),now=datetime.now(UTC))
        if not accepted: raise RetryableProviderError("asset cache reservation was superseded")
        return path,downloaded_key,metadata
def _validate_download_url(url: str, limits: AssetLimits) -> None:
    parsed=urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise ProviderValidationError("asset download URL is unsafe")
    if parsed.port not in (None, 443) or parsed.hostname.casefold() not in {host.casefold() for host in limits.allowed_hosts}:
        raise ProviderValidationError("asset download URL is not an allowed HTTPS host")
    path=unquote(parsed.path)
    if ".." in path.split("/") or not path or path.endswith("/"):
        raise ProviderValidationError("asset download URL has an unsafe filename")
