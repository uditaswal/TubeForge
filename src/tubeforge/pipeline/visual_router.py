"""Deterministic, provider-neutral scene visual strategy selection."""
from __future__ import annotations

from enum import StrEnum
from pydantic import BaseModel, ConfigDict

from tubeforge.domain.contracts import ScenePlan


class VisualStrategy(StrEnum):
    LOCAL_ASSET = "local_asset"
    STOCK_ASSET = "stock_asset"
    GENERATED_STILL = "generated_still"
    GENERATED_VIDEO = "generated_video"
    MOTION_GRAPHICS = "motion_graphics"
    CAPTION_BACKGROUND = "caption_background"


class VisualRoute(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    scene_id: str
    strategy: VisualStrategy
    fallback: VisualStrategy
    rationale: str


class VisualRouter:
    """Prefer existing/licensed assets; always leave a local render fallback."""

    def __init__(self, *, generated_stills_enabled: bool = False, generated_video_enabled: bool = False) -> None:
        self.generated_stills_enabled, self.generated_video_enabled = generated_stills_enabled, generated_video_enabled

    def route(self, scene: ScenePlan, *, visual_source: str = "generated") -> VisualRoute:
        kind = scene.visual_type.casefold()
        if any(word in kind for word in ("text", "chart", "graphic", "diagram")):
            return VisualRoute(scene_id=scene.scene_id, strategy=VisualStrategy.MOTION_GRAPHICS, fallback=VisualStrategy.CAPTION_BACKGROUND, rationale="structured explanatory scene is clearer as local graphics")
        if visual_source == "generated":
            return VisualRoute(scene_id=scene.scene_id, strategy=VisualStrategy.GENERATED_STILL, fallback=VisualStrategy.STOCK_ASSET, rationale="operator selected locally generated scene art")
        if self.generated_video_enabled and "generated-video" in kind:
            return VisualRoute(scene_id=scene.scene_id, strategy=VisualStrategy.GENERATED_VIDEO, fallback=VisualStrategy.STOCK_ASSET, rationale="configured video generation requested for this scene")
        if self.generated_stills_enabled and "generated" in kind:
            return VisualRoute(scene_id=scene.scene_id, strategy=VisualStrategy.GENERATED_STILL, fallback=VisualStrategy.STOCK_ASSET, rationale="configured still generation requested for this scene")
        return VisualRoute(scene_id=scene.scene_id, strategy=VisualStrategy.STOCK_ASSET, fallback=VisualStrategy.CAPTION_BACKGROUND, rationale="licensed/local media is the reliable default")
