"""Semantic scene data; coordinates, fonts and colours belong to the renderer."""
from __future__ import annotations

import re
from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_serializer, model_validator

from .icons import ICON_NAMES
from .logos import LOGO_NAMES

REFERENCE_SHORT_MIN_SECONDS = 25
REFERENCE_SHORT_MAX_SECONDS = 90  # YouTube Shorts allow longer, but retention drops; the preset and gates stop here
IconName = Literal[ICON_NAMES]  # type: ignore[valid-type]
LogoName = Literal[LOGO_NAMES]  # type: ignore[valid-type]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Source(StrictModel):
    source_id: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=42)
    url: HttpUrl


CODE_LANGUAGES = ("rust", "python", "typescript", "javascript", "go", "c", "cpp", "java", "bash", "json", "yaml", "sql", "text")


class StockVisual(StrictModel):
    """Pixabay B-roll behind the scene: a searched clip (default) or portrait photo."""
    kind: Literal["stock"]
    query: str = Field(min_length=3, max_length=60)
    media: Literal["video", "photo"] = "video"


class SourceVisual(StrictModel):
    """Screenshot of the cited source page, cropped to the paragraph that holds ``quote``."""
    kind: Literal["source"]
    quote: str = Field(min_length=8, max_length=160)


class CodeVisual(StrictModel):
    """Short syntax-highlighted snippet that types itself in."""
    kind: Literal["code"]
    language: Literal[CODE_LANGUAGES]  # type: ignore[valid-type]
    lines: tuple[str, ...] = Field(min_length=1, max_length=6)

    @model_validator(mode="after")
    def short_lines(self):
        if any(not line.strip() or len(line) > 30 or "\t" in line for line in self.lines):
            raise ValueError("code lines must be nonempty, tab-free and at most 30 characters")
        return self


Visual = Annotated[StockVisual | SourceVisual | CodeVisual, Field(discriminator="kind")]


class Scene(StrictModel):
    scene_id: str = Field(min_length=1, max_length=64)
    vo: str = Field(min_length=1, max_length=400)
    caption: str = Field(min_length=1, max_length=400)
    source_ids: tuple[str, ...] = Field(default=(), max_length=3)
    reveal_words: tuple[int, ...] = Field(min_length=1, max_length=3)
    # Optional badge from the fixed procedural icon set; never a file or URL.
    icon: IconName | None = None
    # Optional brand logo for a named technology; replaces the icon glyph in the badge.
    logo: LogoName | None = None
    # Optional real imagery for the scene; None keeps the code-drawn template only.
    visual: Visual | None = None

    @model_serializer(mode="wrap")
    def omit_empty_visual(self, handler):
        value = handler(self)
        if self.visual is None:
            value.pop("visual", None)
        if self.logo is None:
            value.pop("logo", None)
        return value

    @model_validator(mode="after")
    def narration_and_anchors(self):
        words = self.vo.split()
        if not 8 <= len(words) <= 15:
            raise ValueError("each scene must contain 8–15 spoken words")
        if tuple(sorted(set(self.reveal_words))) != self.reveal_words or not all(0 <= x < len(words) for x in self.reveal_words):
            raise ValueError("reveal_words must be ordered, distinct narration word indices")
        if "\n" in self.caption:
            raise ValueError("caption input is continuous display text, not a multiline layout")
        return self


class Hook(Scene):
    template: Literal["hook"]
    headline: tuple[str, ...] = Field(min_length=1, max_length=3)
    chips: tuple[str, ...] = Field(default=(), max_length=3)


class BigStat(Scene):
    template: Literal["big_stat"]
    heading: str = Field(min_length=1, max_length=42)
    before: float = Field(ge=0, le=1e9, allow_inf_nan=False)
    after: float = Field(ge=0, le=1e9, allow_inf_nan=False)
    unit: Literal["%", "ms", "s", "x", ""]
    before_label: str = Field(min_length=1, max_length=20)
    after_label: str = Field(min_length=1, max_length=20)

    @model_validator(mode="after")
    def percent_bounds(self):
        if self.unit == "%" and max(self.before, self.after) > 100:
            raise ValueError("percentages cannot exceed 100")
        return self


class BeforeAfter(Scene):
    template: Literal["before_after"]
    heading: str = Field(min_length=1, max_length=42)
    before: str = Field(min_length=1, max_length=42)
    after: str = Field(min_length=1, max_length=42)


class Flow(Scene):
    template: Literal["flow"]
    heading: str = Field(min_length=1, max_length=42)
    nodes: tuple[str, ...] = Field(min_length=2, max_length=3)


class Checklist(Scene):
    template: Literal["checklist"]
    heading: str = Field(min_length=1, max_length=42)
    items: tuple[str, ...] = Field(min_length=1, max_length=3)


class TerminalLine(StrictModel):
    kind: Literal["command", "output"]
    text: str = Field(min_length=1, max_length=60)


class Terminal(Scene):
    template: Literal["terminal"]
    heading: str = Field(min_length=1, max_length=42)
    lines: tuple[TerminalLine, ...] = Field(min_length=1, max_length=3)
    evidence_label: Literal["CAPTURED OUTPUT", "ILLUSTRATIVE OUTPUT", "COMMAND"]


CTA_VERBS = {"follow", "comment", "vote", "pick", "tell", "argue", "drop", "reply"}  # follow ask, or the debate ending's comment prompt


class CTA(Scene):
    template: Literal["cta"]
    chips: tuple[str, ...] = Field(min_length=1, max_length=3)
    headline: str = Field(min_length=1, max_length=48)
    subline: str = Field(min_length=1, max_length=42)

    @model_validator(mode="after")
    def spoken_follow(self):
        normalize = lambda s: " ".join(re.findall(r"\w+", s.casefold()))
        words = normalize(self.headline).split()
        if not words or words[0] not in CTA_VERBS or normalize(self.headline) not in normalize(self.vo):
            raise ValueError("CTA headline must be the follow request or comment prompt present in narration")
        return self


class Loop(Hook):
    """Closing scene that replays the hook's frame so the video loops; no follow or subscribe request anywhere on it."""
    template: Literal["loop"]

    @model_validator(mode="after")
    def no_follow_request(self):
        text = " ".join([self.vo, self.caption, *self.headline, *self.chips]).casefold()
        if re.search(r"\b(follow|subscribe|subscribing|hit the bell|turn on notifications)\b", text):
            raise ValueError("a loop scene must not ask viewers to follow or subscribe; the video simply loops")
        return self


ShortScene = Annotated[Hook | BigStat | BeforeAfter | Flow | Checklist | Terminal | CTA | Loop, Field(discriminator="template")]


class ShortsTopic(StrictModel):
    schema_version: Literal["reference-short-v1"] = "reference-short-v1"
    title: str = Field(min_length=1, max_length=120)
    sources: tuple[Source, ...] = Field(min_length=1, max_length=8)
    scenes: tuple[ShortScene, ...] = Field(min_length=6, max_length=20)

    @model_validator(mode="after")
    def complete_story(self):
        if self.scenes[0].template != "hook" or self.scenes[-1].template not in {"cta", "loop"}:
            raise ValueError("first scene must be hook and last scene must be the loop (or a legacy CTA)")
        if any(s.template in {"hook", "cta", "loop"} for s in self.scenes[1:-1]):
            raise ValueError("hook/loop/CTA cannot replace a teaching scene")
        ids = {s.source_id for s in self.sources}
        if len(ids) != len(self.sources) or len({s.scene_id for s in self.scenes}) != len(self.scenes):
            raise ValueError("scene and source identities must be unique")
        for number, scene in enumerate(self.scenes, 1):
            visual = scene.visual
            if visual is not None and visual.kind in {"source", "code"} and scene.template in {"hook", "cta", "loop"}:
                raise ValueError(f"scene {number}: only stock visuals may sit on the hook, loop or CTA scene")
            if visual is not None and visual.kind == "source" and not scene.source_ids:
                raise ValueError(f"scene {number}: a source screenshot needs the scene to cite a source")
            if not set(scene.source_ids) <= ids:
                raise ValueError(f"scene {number} cites an unknown source")
            if scene.template not in {"hook", "cta", "loop"} and not scene.source_ids:
                raise ValueError(f"every teaching scene requires a source: scene {number} ({scene.template}) has none; "
                                 "give it a factual claim with a source, or move pure opinion into the hook or loop scene")
            count = (len(scene.nodes) if isinstance(scene, Flow) else len(scene.items) if isinstance(scene, Checklist)
                     else len(scene.lines) if isinstance(scene, Terminal) else 2 if isinstance(scene, (BigStat, BeforeAfter))
                     else len(scene.chips) if isinstance(scene, CTA) else 1)
            if len(scene.reveal_words) != count:
                raise ValueError("each visual element needs its own spoken reveal anchor")
        return self
