import io
import json
from pathlib import Path
from urllib.error import HTTPError

import pytest

from tubeforge.core.config import PixabayConfig
from tubeforge.core.errors import ProviderAuthenticationError, ProviderValidationError, RetryableProviderError
from tubeforge.providers.media.pixabay import PixabayClient, RateLimiter, StockAsset


class Clock:
    def __init__(self):
        self.now = 1000.0
        self.slept = []

    def time(self):
        return self.now

    def sleep(self, seconds):
        self.slept.append(seconds)
        self.now += seconds


class Response(io.BytesIO):
    def __init__(self, body, headers=None):
        super().__init__(body)
        self.headers = headers or {}

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def make(tmp_path, responses, per_minute=80, clock=None):
    clock = clock or Clock()
    calls = []

    def opener(request, timeout):
        calls.append(request.full_url)
        item = responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item
    config = PixabayConfig(cache_root=tmp_path / "cache", requests_per_minute=per_minute)
    client = PixabayClient(config, api_key="k", opener=opener, clock=clock.time, sleep=clock.sleep)
    return client, calls, clock


VIDEO_HIT = {"hits": [{"id": 7, "pageURL": "https://pixabay.com/videos/x-7/", "user": "ann", "tags": "server, room", "duration": 12,
                       "videos": {"large": {"url": "https://cdn.pixabay.com/video/a_large.mp4", "width": 1920, "height": 1080, "size": 1},
                                  "medium": {"url": "https://cdn.pixabay.com/video/a_medium.mp4", "width": 1280, "height": 720, "size": 1},
                                  "tiny": {"url": "https://cdn.pixabay.com/video/a_tiny.mp4", "width": 640, "height": 360, "size": 1}}}]}


def test_video_search_picks_smallest_hd_rendition_and_caches(tmp_path):
    client, calls, _ = make(tmp_path, [Response(json.dumps(VIDEO_HIT).encode())])
    first = client.search_videos("server room")
    assert [a.download_url for a in first] == ["https://cdn.pixabay.com/video/a_medium.mp4"]
    assert first[0].evidence()["license_name"] == "Pixabay Content License"
    assert client.search_videos("server room") == first
    assert len(calls) == 1  # second call served from the 24 h cache


def test_rate_limiter_blocks_the_request_over_the_limit(tmp_path):
    clock = Clock()
    limiter = RateLimiter(tmp_path / "rl.json", 3, clock=clock.time, sleep=clock.sleep)
    for _ in range(3):
        limiter.acquire()
    assert clock.slept == []
    limiter.acquire()
    assert 59 < sum(clock.slept) < 62  # waits for the oldest request to leave the 60 s window


def test_rate_limiter_state_is_shared_between_instances(tmp_path):
    clock = Clock()
    a = RateLimiter(tmp_path / "rl.json", 2, clock=clock.time, sleep=clock.sleep)
    b = RateLimiter(tmp_path / "rl.json", 2, clock=clock.time, sleep=clock.sleep)
    a.acquire()
    b.acquire()
    a.acquire()
    assert clock.slept


def test_429_honours_reset_header_then_succeeds(tmp_path):
    limited = HTTPError("u", 429, "Too Many", {"X-RateLimit-Reset": "17", "X-RateLimit-Remaining": "0"}, None)
    client, calls, clock = make(tmp_path, [limited, Response(json.dumps(VIDEO_HIT).encode())])
    assert client.search_videos("a")
    assert len(calls) == 2 and sum(clock.slept) >= 17


def test_low_remaining_header_pauses_the_next_request(tmp_path):
    client, _, clock = make(tmp_path, [Response(json.dumps(VIDEO_HIT).encode(), {"X-RateLimit-Remaining": "1", "X-RateLimit-Reset": "9"}),
                                       Response(json.dumps(VIDEO_HIT).encode())])
    client.search_videos("a")
    client.search_videos("b")
    assert sum(clock.slept) >= 9


def test_bad_key_is_an_authentication_error(tmp_path):
    client, _, _ = make(tmp_path, [HTTPError("u", 403, "Forbidden", {}, None)])
    with pytest.raises(ProviderAuthenticationError):
        client.search_videos("a")


def test_retries_are_bounded(tmp_path):
    client, calls, _ = make(tmp_path, [HTTPError("u", 503, "x", {}, None)] * 10)
    with pytest.raises(RetryableProviderError):
        client.search_videos("a")
    assert len(calls) == client.config.max_retries + 1


def test_download_enforces_host_type_and_size_and_writes_evidence(tmp_path):
    client, _, _ = make(tmp_path, [Response(b"x" * 100)])
    asset = StockAsset("video", "7", "https://pixabay.com/videos/x-7/", "ann", "t", "https://cdn.pixabay.com/video/a.mp4", 1280, 720, 5.0)
    path = client.download(asset)
    assert path.read_bytes() == b"x" * 100 and json.loads(path.with_suffix(".json").read_text())["asset_id"] == "7"
    assert client.download(asset) == path  # cached, no second request
    for bad in ("http://cdn.pixabay.com/a.mp4", "https://evil.example/a.mp4", "https://cdn.pixabay.com/a.exe"):
        with pytest.raises(ProviderValidationError):
            client.download(StockAsset("video", "8", "p", "a", "t", bad, 1, 1, 1.0))


def test_best_prefers_portrait_and_skips_used(tmp_path):
    wide = StockAsset("video", "1", "p", "a", "t", "https://cdn.pixabay.com/1.mp4", 1920, 1080, 10)
    tall = StockAsset("video", "2", "p", "a", "t", "https://cdn.pixabay.com/2.mp4", 1080, 1920, 10)
    assert PixabayClient.best([wide, tall]).asset_id == "2"
    assert PixabayClient.best([wide, tall], exclude={"2"}).asset_id == "1"
    assert PixabayClient.best([], exclude=set()) is None


def test_unavailable_without_key(tmp_path):
    client = PixabayClient(PixabayConfig(cache_root=tmp_path / "c"), api_key="")
    assert not client.available
    with pytest.raises(ProviderValidationError):
        client.search_videos("a")
