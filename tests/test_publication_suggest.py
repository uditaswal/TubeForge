import json
from pathlib import Path

import pytest
from PIL import Image

from tubeforge.domain.contracts import ContentPackage
from tubeforge.pipeline.manual_publish import ManualPublishService
from tubeforge.pipeline.publication_suggest import choose_title, suggest, two_line_description
from tubeforge.pipeline.thumbnail import MAX_BYTES, SIZE, candidate_times, compose, save

FIXTURE = Path(__file__).parent / "fixtures/production/git_stage_commit/content_package.json"


def package() -> ContentPackage:
    return ContentPackage.model_validate_json(FIXTURE.read_text())


def test_title_prefers_a_concrete_stakes_title_over_a_dated_or_cve_one():
    options = ["Run PHP? Read the 21 October 2026 Alert", "CVE-2026-109618 and 109619: What to Do", "PHP Critical Flaw: Fix It or Pull the Plug", "x"]
    assert choose_title(options, "critical bug found in php") == "PHP Critical Flaw: Fix It or Pull the Plug"


def test_description_is_exactly_two_lines_without_angle_brackets():
    description = two_line_description(package())
    lines = description.split("\n")
    assert len(lines) == 2 and all(lines) and len(lines[0]) <= 126 and "<" not in description and ">" not in description


def test_suggestion_has_valid_title_and_thumbnail_text_options():
    value = suggest(package())
    assert 0 < len(value["title"]) <= 100 and value["tags"]


@pytest.mark.parametrize("size", [(1080, 1920), (1920, 1080)])
def test_thumbnail_is_a_16_9_jpeg_under_the_youtube_limit(tmp_path, size):
    frame = Image.effect_noise(size, 60).convert("RGB")
    image = compose(frame, "update php now", "php")
    assert image.size == SIZE
    digest = save(image, tmp_path / "t.jpg")
    assert len(digest) == 64 and 0 < (tmp_path / "t.jpg").stat().st_size <= MAX_BYTES
    assert Image.open(tmp_path / "t.jpg").size == SIZE


def test_candidate_frames_stay_inside_the_video():
    times = candidate_times(30.0)
    assert len(times) == 7 and all(0.5 <= t <= 29.5 for t in times) and times == sorted(times)


def test_draft_metadata_accepts_only_a_sha256_thumbnail_reference_for_youtube():
    base = {"caption": "Two lines.\nSecond.", "title": "A title", "tags": ["php"], "visibility": "private"}
    ManualPublishService._validate_metadata("youtube", {**base, "thumbnail_sha256": "a" * 64})
    for bad in ("short", "G" * 64, 7):
        with pytest.raises(ValueError):
            ManualPublishService._validate_metadata("youtube", {**base, "thumbnail_sha256": bad})
    with pytest.raises(ValueError):
        ManualPublishService._validate_metadata("instagram", {"caption": "x", "thumbnail_sha256": "a" * 64})


def test_youtube_adapter_sets_the_staged_thumbnail_best_effort(tmp_path):
    import httpx
    from tubeforge.providers.publishing.account_youtube import AccountYouTubeAdapter

    digest = "b" * 64
    (tmp_path / "thumbnails").mkdir()
    (tmp_path / "thumbnails" / f"{digest}.jpg").write_bytes(b"\xff\xd8jpeg")
    seen = []

    def handler(request):
        seen.append((request.url.path, request.url.params.get("videoId")))
        return httpx.Response(200, json={})

    adapter = AccountYouTubeAdapter(httpx.Client(transport=httpx.MockTransport(handler)))
    video = tmp_path / ("c" * 64 + ".mp4")
    adapter._apply_thumbnail("vid123", "token", video, {"thumbnail_sha256": digest})
    adapter._apply_thumbnail("vid123", "token", video, {})  # no thumbnail chosen
    adapter._apply_thumbnail("vid123", "token", video, {"thumbnail_sha256": "d" * 64})  # not staged
    assert seen == [("/upload/youtube/v3/thumbnails/set", "vid123")]

    def failing(request):
        raise httpx.ConnectError("down")

    AccountYouTubeAdapter(httpx.Client(transport=httpx.MockTransport(failing)))._apply_thumbnail("v", "t", video, {"thumbnail_sha256": digest})


def test_shorts_thumbnail_is_1080x1920_with_key_content_inside_the_safe_region():
    from tubeforge.core.config import ShortsThumbnailConfig
    from tubeforge.pipeline.thumbnail import compose_portrait, draw_guides

    config = ShortsThumbnailConfig()
    assert config.safe_region == (90, 200, 990, 1560)
    frame = Image.effect_noise((1080, 1920), 40).convert("RGB")
    for text, logo in (("Run a PHP website? Take it down now", "php"), ("Update PHP now", None), ("Why 76 percent of memory bugs survive code review? Rust says no", "rust")):
        image, marks = compose_portrait(frame, text, logo, config=config)
        assert image.size == (1080, 1920) and {"headline", "brand_logo"} <= set(marks)
        x0, y0, x1, y1 = config.safe_region
        for name, (a, b, c, d) in marks.items():
            assert x0 <= a < c <= x1 and y0 <= b < d <= y1, (name, text)
        brand = marks["brand_logo"]
        assert (brand[2] - brand[0]) * (brand[3] - brand[1]) < .06 * 1080 * 1920  # visible, not dominant
        headline = marks["headline"]
        assert abs((headline[0] + headline[2]) / 2 - 540) < 40  # centred
    assert draw_guides(image, config).size == (1080, 1920)


def test_safe_region_is_configurable_and_validated():
    import pytest as _pytest
    from tubeforge.core.config import ShortsThumbnailConfig
    from tubeforge.pipeline.thumbnail import compose_portrait

    wide = ShortsThumbnailConfig(safe_region=(40, 150, 1040, 1700))
    _, marks = compose_portrait(None, "Take it down now", None, config=wide)
    assert all(40 <= m[0] and m[2] <= 1040 and 150 <= m[1] and m[3] <= 1700 for m in marks.values())
    with _pytest.raises(ValueError):
        ShortsThumbnailConfig(safe_region=(90, 200, 1200, 1560))
