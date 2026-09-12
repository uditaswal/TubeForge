"""Platform-specific publication plans derived from one approved master."""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class PlatformVariant(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    profile: str
    platform: str
    aspect_ratio: str = Field(pattern=r"^(16:9|9:16)$")
    source_path: str
    requires_derivative: bool
    title: str
    description: str
    hashtags: tuple[str, ...] = ()


def plan_variants(*, master_path: str, title: str, description: str, tags: list[str] | tuple[str, ...]) -> tuple[PlatformVariant, ...]:
    hashtags = tuple("#" + tag.replace(" ", "") for tag in tags[:8] if tag.strip())
    return (
        PlatformVariant(profile="youtube_landscape", platform="youtube", aspect_ratio="16:9", source_path=master_path, requires_derivative=False, title=title, description=description),
        PlatformVariant(profile="youtube_shorts", platform="youtube", aspect_ratio="9:16", source_path=master_path, requires_derivative=True, title=title, description=description, hashtags=hashtags),
        PlatformVariant(profile="instagram_reels", platform="instagram", aspect_ratio="9:16", source_path=master_path, requires_derivative=True, title=title, description=description, hashtags=hashtags),
        PlatformVariant(profile="facebook_reels", platform="facebook", aspect_ratio="9:16", source_path=master_path, requires_derivative=True, title=title, description=description, hashtags=hashtags),
        PlatformVariant(profile="snapchat_handoff", platform="snapchat", aspect_ratio="9:16", source_path=master_path, requires_derivative=True, title=title, description=description, hashtags=hashtags),
    )
