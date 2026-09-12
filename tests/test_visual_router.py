from tubeforge.domain.contracts import ScenePlan
from tubeforge.pipeline.visual_router import VisualRouter, VisualStrategy


def test_visual_router_prefers_local_graphics_and_reliable_stock_fallback() -> None:
    router = VisualRouter()
    graphic = router.route(ScenePlan(scene_id="chart", visual_type="animated chart graphic", search_queries=("chart",), fallback_visual="gradient"))
    footage = router.route(ScenePlan(scene_id="footage", visual_type="b-roll", search_queries=("rain",), fallback_visual="gradient"))
    assert graphic.strategy is VisualStrategy.MOTION_GRAPHICS
    assert footage.strategy is VisualStrategy.STOCK_ASSET
    assert footage.fallback is VisualStrategy.CAPTION_BACKGROUND
