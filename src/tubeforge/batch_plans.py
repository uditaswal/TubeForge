"""Bounded markdown batch intake. Narration is opaque operator-supplied text."""
from __future__ import annotations

import re
from datetime import datetime
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, HttpUrl, ValidationError


class Beat(BaseModel):
    model_config = ConfigDict(extra="forbid")
    t: float = Field(ge=0, le=90)
    point: str = Field(min_length=1)


class Thumbnail(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = ""
    visual: str = ""


class BatchShort(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(pattern=r"^[a-z0-9-]+$", max_length=120)
    title: str = Field(min_length=1, max_length=100)
    concept: str = Field(min_length=1)
    beats: list[Beat] = Field(min_length=1)
    length_s: int = Field(default=60, ge=30, le=90, strict=True)
    ending: Literal["loop", "debate"] = "loop"
    channel: str | None = None
    publish_at: datetime | None = None
    hook: str = ""
    cta: str = ""
    claims_to_verify: list[str] = Field(default_factory=list)
    sources: list[HttpUrl] = Field(default_factory=list)
    thumbnail: Thumbnail = Field(default_factory=Thumbnail)
    tags: list[str] = Field(default_factory=list)
    narration: str | None = None


class BatchError(BaseModel):
    line: int
    message: str


class BatchPlan(BaseModel):
    shorts: list[BatchShort] = Field(default_factory=list)
    errors: list[BatchError] = Field(default_factory=list)


def parse_batch(markdown: str) -> BatchPlan:
    """Parse one YAML block per level-two section; never return partial commits."""
    result = BatchPlan()
    if len(markdown.encode("utf-8")) > 2_000_000:
        result.errors.append(BatchError(line=1, message="file exceeds 2 MB"))
        return result
    lines = markdown.splitlines()
    headings = [i for i, line in enumerate(lines) if re.match(r"^##\s+\S", line)]
    if not headings:
        result.errors.append(BatchError(line=1, message="expected a ## heading and fenced yaml block"))
    seen: set[str] = set()
    for n, start in enumerate(headings):
        end = headings[n + 1] if n + 1 < len(headings) else len(lines)
        fences = [i for i in range(start + 1, end) if re.fullmatch(r"\s*```yaml\s*", lines[i])]
        if len(fences) != 1:
            result.errors.append(BatchError(line=start + 1, message="expected exactly one fenced yaml block"))
            continue
        opening = fences[0]
        closing = next((i for i in range(opening + 1, end) if re.fullmatch(r"\s*```\s*", lines[i])), None)
        if closing is None:
            result.errors.append(BatchError(line=opening + 1, message="unclosed yaml block"))
            continue
        source = "\n".join(lines[opening + 1:closing]) + "\n"
        try:
            node = yaml.compose(source, Loader=yaml.SafeLoader)
            if not isinstance(node, yaml.MappingNode):
                raise ValueError("short must be a YAML mapping")
            keys: dict[str, int] = {}
            for key, _ in node.value:
                if key.value in keys:
                    raise ValueError(f"duplicate YAML field: {key.value}")
                keys[key.value] = opening + 2 + key.start_mark.line
            short = BatchShort.model_validate(yaml.safe_load(source))
            if short.id in seen:
                result.errors.append(BatchError(line=keys["id"], message=f"duplicate id: {short.id}"))
            else:
                seen.add(short.id)
                result.shorts.append(short)
        except ValidationError as error:
            for item in error.errors():
                field = str(item["loc"][0]) if item["loc"] else "short"
                result.errors.append(BatchError(line=keys.get(field, opening + 2), message=f"{field}: {item['msg']}"))
        except yaml.YAMLError as error:
            mark = getattr(error, "problem_mark", None)
            result.errors.append(BatchError(line=opening + 2 + (mark.line if mark else 0), message="invalid YAML"))
        except (ValueError, RecursionError) as error:
            result.errors.append(BatchError(line=opening + 2, message=str(error)))
    return result
