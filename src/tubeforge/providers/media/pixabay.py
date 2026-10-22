"""Pixabay stock photo/video client with a cross-process rate limiter and a 24 h search cache.

Pixabay allows 100 requests per 60 s per API key (not per IP) and reports the state in
``X-RateLimit-*`` headers. Several TubeForge processes (worker, preparation child processes)
may share one key, so the limiter state lives in a lock-protected file next to the cache.
Results are cached on disk (Pixabay's terms require it) and files are downloaded, never hotlinked.
Every returned asset carries the evidence the publication record needs (id, page URL, author, licence).
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import logging
import os
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener

from tubeforge.core.config import PixabayConfig, REPOSITORY_ROOT
from tubeforge.core.errors import ProviderAuthenticationError, ProviderValidationError, RetryableProviderError

LOG = logging.getLogger(__name__)
KEY_ENV = "TUBEFORGE_PIXABAY_API_KEY"
LICENSE = "Pixabay Content License"
LICENSE_URL = "https://pixabay.com/service/license-summary/"
USER_AGENT = "TubeForge/0.1 (+local; stock b-roll)"
WINDOW_SECONDS = 60.0
MAX_WAIT_SECONDS = 65.0


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):  # downloads must come from the allow-listed host directly
        return None


@dataclass(frozen=True)
class StockAsset:
    kind: str  # "video" | "image"
    asset_id: str
    page_url: str
    author: str
    tags: str
    download_url: str
    width: int
    height: int
    duration: float | None
    license_name: str = LICENSE
    license_url: str = LICENSE_URL

    def evidence(self) -> dict[str, Any]:
        return {**asdict(self), "provider": "pixabay"}


class RateLimiter:
    """Sliding-window limiter shared by every process that uses the same cache directory."""

    def __init__(self, path: Path, per_minute: int, *, clock: Callable[[], float] = time.time,
                 sleep: Callable[[float], None] = time.sleep) -> None:
        self.path, self.per_minute, self.clock, self.sleep = path, per_minute, clock, sleep
        path.parent.mkdir(parents=True, exist_ok=True)

    def _locked(self, work):
        with open(self.path, "a+", encoding="utf-8") as stream:
            fcntl.flock(stream, fcntl.LOCK_EX)
            try:
                stream.seek(0)
                try:
                    state = json.loads(stream.read() or "{}")
                except json.JSONDecodeError:
                    state = {}
                result = work(state)
                stream.seek(0)
                stream.truncate()
                stream.write(json.dumps(state))
                stream.flush()
                return result
            finally:
                fcntl.flock(stream, fcntl.LOCK_UN)

    def acquire(self) -> None:
        """Block until one more request fits in the window and any server-announced pause has passed."""
        while True:
            def attempt(state):
                now = self.clock()
                stamps = [t for t in state.get("stamps", []) if now - t < WINDOW_SECONDS]
                wait = max(0.0, state.get("blocked_until", 0.0) - now)
                if not wait and len(stamps) >= self.per_minute:
                    wait = WINDOW_SECONDS - (now - min(stamps)) + .05
                if wait <= 0:
                    stamps.append(now)
                state["stamps"] = stamps
                return wait
            wait = self._locked(attempt)
            if wait <= 0:
                return
            LOG.info("pixabay rate limit: waiting %.1fs", wait)
            self.sleep(min(wait, MAX_WAIT_SECONDS))

    def observe(self, remaining: str | None, reset: str | None, *, throttled: bool = False) -> None:
        """Record ``X-RateLimit-Remaining/Reset`` so sibling processes pause when the window is nearly spent."""
        try:
            left = int(remaining) if remaining is not None else None
            seconds = float(reset) if reset is not None else None
        except ValueError:
            return
        if not throttled and not (left is not None and left <= 1 and seconds):
            return
        pause = min(seconds if seconds else WINDOW_SECONDS, MAX_WAIT_SECONDS)
        self._locked(lambda state: state.__setitem__("blocked_until", max(state.get("blocked_until", 0.0), self.clock() + pause)))


class PixabayClient:
    def __init__(self, config: PixabayConfig, *, api_key: str | None = None,
                 limiter: RateLimiter | None = None, opener=None,
                 clock: Callable[[], float] = time.time, sleep: Callable[[float], None] = time.sleep) -> None:
        self.config = config
        self._key = api_key if api_key is not None else os.environ.get(KEY_ENV, "")
        root = Path(config.cache_root)
        self.root = root if root.is_absolute() else REPOSITORY_ROOT / root
        (self.root / "search").mkdir(parents=True, exist_ok=True)
        (self.root / "files").mkdir(parents=True, exist_ok=True)
        self.limiter = limiter or RateLimiter(self.root / "ratelimit.json", config.requests_per_minute, clock=clock, sleep=sleep)
        self._open = opener or build_opener(_NoRedirect()).open
        self.clock, self.sleep = clock, sleep
        self.requests_made = 0

    @property
    def available(self) -> bool:
        return self.config.enabled and bool(self._key)

    # -- HTTP ---------------------------------------------------------------------------
    def _request(self, url: str, *, stream_to: Path | None = None) -> bytes | None:
        last: Exception | None = None
        for attempt in range(self.config.max_retries + 1):
            self.limiter.acquire()
            self.requests_made += 1
            try:
                with self._open(Request(url, headers={"User-Agent": USER_AGENT}), timeout=self.config.timeout_seconds) as response:
                    self.limiter.observe(response.headers.get("X-RateLimit-Remaining"), response.headers.get("X-RateLimit-Reset"))
                    if stream_to is None:
                        return response.read(5_000_000)
                    written = 0
                    with open(stream_to, "wb") as out:
                        while chunk := response.read(1 << 16):
                            written += len(chunk)
                            if written > self.config.max_download_bytes:
                                raise ProviderValidationError("Pixabay download exceeds the configured size limit")
                            out.write(chunk)
                    return None
            except HTTPError as error:
                if error.code in (401, 403) and stream_to is None:
                    raise ProviderAuthenticationError("Pixabay rejected the API key") from error
                if error.code == 429:
                    self.limiter.observe(error.headers.get("X-RateLimit-Remaining"), error.headers.get("X-RateLimit-Reset")
                                         or error.headers.get("Retry-After"), throttled=True)
                    last = error
                elif error.code >= 500:
                    last = error
                    self.sleep(min(2 ** attempt, 10))
                else:
                    raise RetryableProviderError(f"Pixabay request failed with HTTP {error.code}") from error
            except (URLError, TimeoutError, OSError) as error:
                last = error
                self.sleep(min(2 ** attempt, 10))
        raise RetryableProviderError(f"Pixabay unavailable after retries: {type(last).__name__}")

    def _search(self, endpoint: str, params: dict[str, Any]) -> dict[str, Any]:
        if not self.available:
            raise ProviderValidationError("Pixabay is disabled or has no API key")
        query = urlencode(sorted(params.items()))
        cache = self.root / "search" / (hashlib.sha256(f"{endpoint}?{query}".encode()).hexdigest() + ".json")
        if cache.is_file() and self.clock() - cache.stat().st_mtime < self.config.search_cache_hours * 3600:
            return json.loads(cache.read_text())
        body = self._request(f"{endpoint}?{urlencode({'key': self._key, **params})}")
        try:
            data = json.loads(body or b"{}")
        except json.JSONDecodeError as error:
            raise RetryableProviderError("Pixabay returned invalid JSON") from error
        if not isinstance(data, dict) or "hits" not in data:
            raise RetryableProviderError("Pixabay returned an unexpected response")
        temporary = cache.with_suffix(".tmp")
        temporary.write_text(json.dumps(data))
        temporary.replace(cache)
        return data

    # -- search -------------------------------------------------------------------------
    def search_videos(self, query: str, *, per_page: int = 20) -> list[StockAsset]:
        data = self._search(self.config.video_api_url, {"q": query[:100], "video_type": "film", "safesearch": "true",
                                                        "per_page": per_page, "order": "popular"})
        assets = []
        for hit in data["hits"]:
            renditions = [v for v in (hit.get("videos") or {}).values() if isinstance(v, dict) and v.get("url")]
            # Smallest rendition that still meets the quality floor keeps decode time and disk use low.
            usable = sorted((v for v in renditions if v.get("height", 0) >= self.config.min_video_height),
                            key=lambda v: v["height"])
            if not usable:
                continue
            chosen = usable[0]
            assets.append(StockAsset("video", str(hit["id"]), hit["pageURL"], str(hit.get("user", "")), str(hit.get("tags", "")),
                                     chosen["url"], int(chosen["width"]), int(chosen["height"]), float(hit.get("duration") or 0)))
        return assets

    def search_images(self, query: str, *, per_page: int = 20) -> list[StockAsset]:
        data = self._search(self.config.image_api_url, {"q": query[:100], "image_type": "photo", "orientation": "vertical",
                                                        "safesearch": "true", "per_page": per_page, "min_height": 1280, "order": "popular"})
        return [StockAsset("image", str(h["id"]), h["pageURL"], str(h.get("user", "")), str(h.get("tags", "")),
                           h["largeImageURL"], int(h.get("imageWidth") or 0), int(h.get("imageHeight") or 0), None)
                for h in data["hits"] if h.get("largeImageURL")]

    @staticmethod
    def best(assets: list[StockAsset], *, min_duration: float = 0.0, exclude: set[str] = frozenset()) -> StockAsset | None:
        """Prefer portrait, long enough, high-resolution clips; skip assets already used in this video."""
        def score(a: StockAsset) -> float:
            portrait = 1.0 if a.height >= a.width else .55
            long_enough = 1.0 if (a.duration is None or a.duration >= min_duration) else .6
            return portrait * long_enough * min(a.height, 1920) / 1920
        pool = [a for a in assets if a.asset_id not in exclude]
        return max(pool, key=score, default=None)

    # -- download -----------------------------------------------------------------------
    def download(self, asset: StockAsset) -> Path:
        parsed = urlparse(asset.download_url)
        if parsed.scheme != "https" or not (parsed.hostname or "").endswith("pixabay.com"):
            raise ProviderValidationError("Pixabay download URL is outside the allowed host")
        extension = Path(parsed.path).suffix.lower()
        if extension not in {".mp4", ".webm", ".jpg", ".jpeg", ".png"}:
            raise ProviderValidationError("Pixabay download has an unsupported file type")
        destination = self.root / "files" / f"{asset.kind}-{asset.asset_id}{extension}"
        if destination.is_file() and destination.stat().st_size > 0:
            return destination
        temporary = destination.with_suffix(destination.suffix + ".part")
        try:
            self._request(asset.download_url, stream_to=temporary)
            if temporary.stat().st_size == 0:
                raise RetryableProviderError("Pixabay returned an empty file")
            temporary.replace(destination)
        finally:
            temporary.unlink(missing_ok=True)
        (destination.with_suffix(".json")).write_text(json.dumps(asset.evidence(), indent=2))
        return destination
