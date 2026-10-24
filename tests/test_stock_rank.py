"""Local stock ranking must prioritize topic relevance under rights limits."""
from tubeforge.providers.media.pixabay import StockAsset
from tubeforge.providers.media.stock_rank import rank_assets


def asset(asset_id, tags, *, width=1280, height=720, duration=8.0, license_name="Pixabay Content License"):
    return StockAsset("video", asset_id, f"https://pixabay.com/videos/id-{asset_id}/", "fixture",
                      tags, f"https://cdn.pixabay.com/{asset_id}.mp4", width, height, duration,
                      license_name=license_name)


def test_relevant_asset_beats_large_generic_or_unlicensed_asset():
    candidates = [asset("rocket", "technology science space rocket", width=1920, height=1080),
                  asset("android", "android code software developer"),
                  asset("unlicensed", "android code software", license_name="unknown")]
    ranked = rank_assets(candidates, query="android code", scene_text="Android code became safer")
    assert [row["asset_id"] for row in ranked] == ["android"]
    assert ranked[0]["matched_terms"] == ["android", "code"]


def test_diversity_breaks_relevance_tie_without_reusing_an_id():
    repeated = asset("1", "android code laptop typing")
    varied = asset("2", "android code developer screen")
    ranked = rank_assets([repeated, varied], query="android code", scene_text="Android code",
                         previous_tags=(repeated.tags,))
    assert [row["asset_id"] for row in ranked] == ["2", "1"]
    assert [row["asset_id"] for row in rank_assets([repeated, varied], query="android code",
           scene_text="Android code", used_ids={"2"})] == ["1"]


def test_duration_resolution_and_page_provenance_are_eligibility_gates():
    short = asset("short", "android code", duration=2)
    tiny = asset("tiny", "android code", width=320, height=240)
    outside = StockAsset("video", "outside", "https://example.com/x", "fixture", "android code",
                         "https://example.com/x.mp4", 1280, 720, 8.0)
    assert rank_assets([short, tiny, outside], query="android code", scene_text="Android code") == []
