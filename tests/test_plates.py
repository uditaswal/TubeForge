import json

import pytest
from pydantic import TypeAdapter, ValidationError

from test_reference_shorts import topic_data
from tubeforge.pipeline.plates import prepare_plates
from tubeforge.rendering.shorts.plates import CARD, Plates, card_indices, code_card
from tubeforge.rendering.shorts.schema import CodeVisual, ShortsTopic, Visual

VISUAL = TypeAdapter(Visual)


def topic_with(visuals):
    data = topic_data()
    for index, visual in visuals.items():
        data["scenes"][index]["visual"] = visual
    return ShortsTopic.model_validate(data)


CODE = {"kind": "code", "language": "rust", "lines": ["fn main() {", "    run();", "}"]}


def test_scenes_without_visual_serialize_as_before():
    assert "visual" not in json.loads(topic_with({}).model_dump_json())["scenes"][0]
    assert json.loads(topic_with({1: CODE}).model_dump_json())["scenes"][1]["visual"]["kind"] == "code"


@pytest.mark.parametrize("bad", [
    {"kind": "code", "language": "rust", "lines": ["x" * 31]},
    {"kind": "code", "language": "cobol", "lines": ["x"]},
    {"kind": "code", "language": "rust", "lines": []},
    {"kind": "stock", "query": "ab"},
    {"kind": "source", "quote": "short"},
])
def test_invalid_visuals_are_rejected(bad):
    with pytest.raises(ValidationError):
        VISUAL.validate_python(bad)


def test_source_and_code_cannot_sit_on_hook_or_cta_and_source_needs_a_cited_source():
    with pytest.raises(ValidationError, match="only stock visuals"):
        topic_with({0: CODE})
    with pytest.raises(ValidationError, match="only stock visuals"):
        topic_with({6: {"kind": "source", "quote": "a quote that is long enough"}})
    data = topic_data()
    data["scenes"][1]["source_ids"] = []
    data["scenes"][1]["visual"] = {"kind": "source", "quote": "a quote that is long enough"}
    with pytest.raises(ValidationError):
        ShortsTopic.model_validate(data)


def test_code_card_fits_the_card_zone_and_typing_reveals_more_pixels():
    visual = VISUAL.validate_python(CODE)
    full, half = code_card(visual), code_card(visual, 8)
    assert full.width - 56 == CARD[2] - CARD[0] and full.height - 56 <= CARD[3] - CARD[1]
    assert full.getbbox() and half.tobytes() != full.tobytes()


def test_card_indices_include_code_always_and_source_only_when_captured():
    quote = {"kind": "source", "quote": "a quote that is long enough"}
    topic = topic_with({1: CODE, 2: quote, 3: quote})
    manifest = {"scenes": {"2": {"kind": "source", "file": "plates/source-2.png"}, "3": {"kind": "none", "reason": "blocked"}}}
    assert card_indices(topic, manifest) == frozenset({1, 2})


def test_prepare_never_fails_the_job(tmp_path):
    topic = topic_with({1: CODE, 2: {"kind": "stock", "query": "server room"}, 3: {"kind": "source", "quote": "a quote that is long enough"}})
    manifest = prepare_plates(topic, tmp_path, pixabay=None, capture=None)
    kinds = {k: v["kind"] for k, v in manifest["scenes"].items()}
    assert kinds == {"1": "code", "2": "none", "3": "none"}
    assert json.loads((tmp_path / "plates" / "manifest.json").read_text())["scenes"]["2"]["reason"]
    plates = Plates(topic, tmp_path, manifest)
    assert plates.background(2, 0.5, 4.0) is None and plates.card(1, 1.0, 4.0, None) is not None


def test_logo_scene_renders_a_light_badge_and_rejects_unknown_slugs():
    from PIL import Image
    from tubeforge.rendering.shorts.logos import LOGO_NAMES, logo_badge

    assert {"php", "nodedotjs", "docker", "rust"} <= set(LOGO_NAMES)
    badge = logo_badge("php", 200)
    assert badge.size == (200, 200) and badge.getpixel((100, 100))[3] == 255
    assert badge.getpixel((100, 6))[:3] != (0, 0, 0)  # disc is light, not black
    data = topic_data()
    data["scenes"][1]["logo"] = "php"
    assert json.loads(ShortsTopic.model_validate(data).model_dump_json())["scenes"][1]["logo"] == "php"
    data["scenes"][1]["logo"] = "not-a-logo"
    with pytest.raises(ValidationError):
        ShortsTopic.model_validate(data)
    with pytest.raises(ValueError):
        logo_badge("not-a-logo", 100)


def test_stock_library_serves_repeated_queries_without_network(tmp_path):
    from tubeforge.core.config import PixabayConfig
    from tubeforge.providers.media.pixabay import PixabayClient, StockAsset

    client = PixabayClient(PixabayConfig(cache_root=tmp_path), api_key="")
    assert not client.available
    asset = StockAsset("video", "42", "https://pixabay.com/videos/42", "someone", "server, data center, network, racks", "https://cdn.pixabay.com/x.mp4", 1080, 1920, 12.0)
    file = client.library.files / "video-42.mp4"
    file.write_bytes(b"x")
    client.library.add(asset, file, "server room racks")
    found = client.library.find("server racks", "video", min_duration=4.0)
    assert found is not None and found[0].asset_id == "42" and found[1] == file
    assert client.library.find("server racks", "video", exclude={"42"}) is None
    assert client.library.find("rocket launch", "video") is None
    assert client.library.find("server racks", "video", min_duration=30.0) is None
    manifest = prepare_plates(topic_with({1: {"kind": "stock", "query": "server racks", "media": "video"}}), tmp_path / "job", pixabay=client, capture=None)
    entry = manifest["scenes"]["1"]
    assert entry["kind"] == "stock" and entry["origin"] == "local-library" and client.requests_made == 0
