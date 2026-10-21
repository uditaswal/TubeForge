"""Semantic scene data; coordinates, fonts and colours belong to the renderer."""
from __future__ import annotations

import re
from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Source(StrictModel):
    source_id: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=42)
    url: HttpUrl


class Scene(StrictModel):
    scene_id: str = Field(min_length=1, max_length=64)
    vo: str = Field(min_length=1, max_length=400)
    caption: str = Field(min_length=1, max_length=400)
    source_ids: tuple[str, ...] = Field(default=(), max_length=3)
    reveal_words: tuple[int, ...] = Field(min_length=1, max_length=3)

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


class CTA(Scene):
    template: Literal["cta"]
    chips: tuple[str, ...] = Field(min_length=1, max_length=3)
    headline: str = Field(min_length=1, max_length=48)
    subline: str = Field(min_length=1, max_length=42)

    @model_validator(mode="after")
    def spoken_follow(self):
        normalize = lambda s: " ".join(re.findall(r"\w+", s.casefold()))
        if not normalize(self.headline).startswith("follow") or normalize(self.headline) not in normalize(self.vo):
            raise ValueError("CTA headline must be the follow request present in narration")
        return self


ShortScene = Annotated[Hook | BigStat | BeforeAfter | Flow | Checklist | Terminal | CTA, Field(discriminator="template")]


class ShortsTopic(StrictModel):
    schema_version: Literal["reference-short-v1"] = "reference-short-v1"
    title: str = Field(min_length=1, max_length=120)
    sources: tuple[Source, ...] = Field(min_length=1, max_length=8)
    scenes: tuple[ShortScene, ...] = Field(min_length=6, max_length=8)

    @model_validator(mode="after")
    def complete_story(self):
        if self.scenes[0].template != "hook" or self.scenes[-1].template != "cta":
            raise ValueError("first scene must be hook and last scene must be CTA")
        if any(s.template in {"hook", "cta"} for s in self.scenes[1:-1]):
            raise ValueError("hook/CTA cannot replace a teaching scene")
        ids = {s.source_id for s in self.sources}
        if len(ids) != len(self.sources) or len({s.scene_id for s in self.scenes}) != len(self.scenes):
            raise ValueError("scene and source identities must be unique")
        for scene in self.scenes:
            if not set(scene.source_ids) <= ids:
                raise ValueError("scene cites an unknown source")
            if scene.template not in {"hook", "cta"} and not scene.source_ids:
                raise ValueError("every teaching scene requires a source")
            count = (len(scene.nodes) if isinstance(scene, Flow) else len(scene.items) if isinstance(scene, Checklist)
                     else len(scene.lines) if isinstance(scene, Terminal) else 2 if isinstance(scene, (BigStat, BeforeAfter))
                     else len(scene.chips) if isinstance(scene, CTA) else 1)
            if len(scene.reveal_words) != count:
                raise ValueError("each visual element needs its own spoken reveal anchor")
        return self
