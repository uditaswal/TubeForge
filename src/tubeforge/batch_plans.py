"""Bounded markdown batch intake. Narration is opaque operator-supplied text."""
from __future__ import annotations

import re
from datetime import datetime
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, HttpUrl, ValidationError, model_validator


_RANGE = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*(?:-|\u2013|to)\s*(\d+(?:\.\d+)?)\s*s?\s*$")


class Beat(BaseModel):
    """One outline beat. ``t`` is the start second; a range such as ``"0-10"`` is accepted and keeps its end."""
    model_config = ConfigDict(extra="ignore")
    t: float = Field(ge=0, le=120)
    end: float | None = Field(default=None, ge=0, le=120)
    point: str = Field(min_length=1)

    @model_validator(mode="before")
    @classmethod
    def accept_ranges(cls, data):
        if isinstance(data, dict) and isinstance(data.get("t"), str):
            found = _RANGE.match(data["t"])
            if found and float(found.group(2)) > float(found.group(1)):
                return {**data, "t": float(found.group(1)), "end": float(found.group(2))}
        return data


class Thumbnail(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = ""
    visual: str = ""


class BatchShort(BaseModel):
    # An unknown field is noted and ignored, not rejected: the writer can work without it.
    model_config = ConfigDict(extra="ignore")
    id: str = Field(pattern=r"^[a-z0-9-]+$", max_length=120)
    title: str = Field(min_length=1, max_length=100)
    concept: str = Field(min_length=1)
    beats: list[Beat] = Field(default_factory=list)  # optional: the writer can infer the structure from the concept
    length_s: int = Field(default=60, ge=30, le=120, strict=True)
    ending: Literal["loop", "debate"] = "loop"
    channel: str | None = None
    publish_at: datetime | None = None
    hook: str = ""
    cta: str = ""
    claims_to_verify: list[str] = Field(default_factory=list)
    sources: list[HttpUrl] = Field(default_factory=list)
    thumbnail: Thumbnail = Field(default_factory=Thumbnail)
    tags: list[str] = Field(default_factory=list)
    narration: str | None = Field(default=None, max_length=12_000)
    # exact = use the script word for word (either writer): no rewriting, no writing checks.
    script_mode: Literal["assist", "exact"] | None = None   # None: the import's choice, then the Settings default

    @model_validator(mode="after")
    def exact_needs_a_script(self):
        if self.script_mode == "exact" and not (self.narration or "").strip():
            raise ValueError("script_mode: exact needs a script (or narration) in the same block")
        return self

    @model_validator(mode="before")
    @classmethod
    def accept_script_alias(cls, data):
        """``script:`` is the obvious name for the operator's own narration; it means exactly ``narration:``."""
        if isinstance(data, dict) and "script" in data:
            if "narration" in data:
                raise ValueError("give your script once: use either `script` or `narration`, not both")
            data = {**data, "narration": data["script"]}
            del data["script"]
        return data


class BatchError(BaseModel):
    line: int
    message: str


class BatchPlan(BaseModel):
    shorts: list[BatchShort] = Field(default_factory=list)
    errors: list[BatchError] = Field(default_factory=list)
    # Things that were fixed or ignored so the import could go ahead; shown to the operator, never blocking.
    warnings: list[BatchError] = Field(default_factory=list)


_KNOWN_FIELDS = set(BatchShort.model_fields) | {"script"}


def _slug(value: str) -> str:
    return re.sub(r"-{2,}", "-", re.sub(r"[^a-z0-9]+", "-", str(value).lower())).strip("-")[:120]


def _seconds(value, low=0.0, high=120.0):
    """A time as seconds: 12, "12", "12s", "0:12" or "1:05" (clamped to the allowed range)."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        number = float(value)
    else:
        text = str(value).strip().lower().rstrip("s").strip()
        if re.fullmatch(r"\d+:\d{1,2}(?::\d{1,2})?", text):
            parts = [int(p) for p in text.split(":")]
            number = float(sum(p * 60 ** i for i, p in enumerate(reversed(parts))))
        else:
            try:
                number = float(text)
            except ValueError:
                return None
    return min(max(number, low), high)


def _normalize(raw: dict, heading: str, line: int, taken: set[str], warn) -> dict:
    """Repair what a person (or an AI) is likely to get slightly wrong. The writer fills in what is missing."""
    data = {key: value for key, value in raw.items() if value is not None}
    for key in list(data):
        if key not in _KNOWN_FIELDS:
            warn(line, f"ignored the unknown field `{key}`")
            del data[key]
    title = str(data.get("title") or "").strip()
    if not title:
        title = re.sub(r"^#+\s*", "", heading).strip() or str(data.get("id") or "Untitled short")
        warn(line, "no title: used the heading")
    if len(title) > 100:
        warn(line, "title shortened to 100 characters")
        title = title[:100].rstrip()
    data["title"] = title
    identifier = str(data.get("id") or "").strip()
    slug = _slug(identifier) if identifier else _slug(title)
    if not slug:
        slug = "short"
    if slug != identifier:
        warn(line, f"id set to `{slug}`" + ("" if not identifier else f" (was `{identifier}`)"))
    candidate, number = slug, 2
    while candidate in taken:
        candidate = f"{slug[:112]}-{number}"
        number += 1
    if candidate != slug:
        warn(line, f"id `{slug}` was already used: renamed to `{candidate}`")
    data["id"] = candidate
    if not str(data.get("concept") or "").strip():
        data["concept"] = title
        warn(line, "no concept: used the title")
    beats = []
    for index, item in enumerate(data.get("beats") or []):
        if isinstance(item, dict):
            point = next((str(item[k]).strip() for k in ("point", "text", "beat", "what", "idea") if item.get(k)), "")
            when = next((item[k] for k in ("t", "time", "at", "start") if item.get(k) is not None), None)
            beat = {"point": point or "(beat)"}
            if isinstance(when, str) and _RANGE.match(when):
                beat["t"] = when
            else:
                seconds = _seconds(when) if when is not None else None
                beat["t"] = seconds if seconds is not None else float(index * 10)
        else:
            beat = {"t": float(index * 10), "point": str(item).strip() or "(beat)"}
        beats.append(beat)
    data["beats"] = beats
    if "length_s" in data:
        seconds = _seconds(data["length_s"], 30, 120)
        if seconds is None:
            warn(line, "length_s was not a number: used 60")
            seconds = 60
        elif seconds != _seconds(data["length_s"], 0, 100000):
            warn(line, f"length_s set to {int(seconds)} (the allowed range is 30 to 120)")
        data["length_s"] = int(round(seconds))
    ending = str(data.get("ending") or "loop").strip().lower()
    if ending not in {"loop", "debate"}:
        warn(line, f"ending `{ending}` is not loop or debate: used loop")
        ending = "loop"
    data["ending"] = ending
    if data.get("publish_at") is not None:
        try:
            datetime.fromisoformat(str(data["publish_at"]).replace("Z", "+00:00")) if not isinstance(data["publish_at"], datetime) else None
        except ValueError:
            warn(line, "publish_at was not a date and time: ignored")
            del data["publish_at"]
    for key in ("tags", "claims_to_verify", "sources"):
        value = data.get(key)
        if value is None:
            continue
        if isinstance(value, str):
            value = [part.strip() for part in re.split(r"[,\n]", value) if part.strip()]
        data[key] = [str(item).strip() for item in value if str(item).strip()]
    good = []
    for url in data.get("sources", []):
        if re.match(r"^https?://\S+$", url):
            good.append(url)
        else:
            warn(line, f"source `{url[:60]}` is not an http(s) link: ignored")
    if "sources" in data:
        data["sources"] = good
    thumbnail = data.get("thumbnail")
    if isinstance(thumbnail, str):
        data["thumbnail"] = {"text": thumbnail}
    elif isinstance(thumbnail, dict):
        data["thumbnail"] = {k: str(v) for k, v in thumbnail.items() if k in {"text", "visual"} and v is not None}
    elif thumbnail is not None:
        del data["thumbnail"]
    if data.get("script_mode") not in (None, "assist", "exact"):
        warn(line, f"script_mode `{data['script_mode']}` is not assist or exact: ignored")
        del data["script_mode"]
    if data.get("script_mode") == "exact" and not (str(data.get("narration") or data.get("script") or "")).strip():
        warn(line, "script_mode exact needs a script: used assist")
        del data["script_mode"]
    for key in ("hook", "cta", "channel"):
        if key in data and not isinstance(data[key], str):
            data[key] = str(data[key])
    return data


_OPEN = re.compile(r"^\s*(?:```|~~~)\s*(yaml|yml)?\s*$", re.IGNORECASE)
_CLOSE = re.compile(r"^\s*(?:```|~~~)\s*$")


def _blocks(lines: list[str], start: int, end: int, warn):
    """(first line number, yaml text) for every yaml block in the section; an unclosed one runs to the section's end."""
    found, i = [], start
    while i < end:
        match = _OPEN.match(lines[i])
        if match and (match.group(1) or not found):
            closing = next((k for k in range(i + 1, end) if _CLOSE.match(lines[k])), None)
            if closing is None:
                warn(i + 1, "the yaml block was not closed: read to the end of the section")
                closing = end
            found.append((i + 1, "\n".join(lines[i + 1:closing]) + "\n"))
            i = closing + 1
        else:
            i += 1
    return found


def _load(text: str, first_line: int, warn):
    """Read yaml; when that fails, keep the simple `key: value` lines instead of rejecting the whole short."""
    try:
        node = yaml.compose(text, Loader=yaml.SafeLoader)
        if isinstance(node, yaml.MappingNode):
            seen = set()
            for key, _ in node.value:
                if key.value in seen:
                    warn(first_line + key.start_mark.line, f"`{key.value}` appears twice: the last one is used")
                seen.add(key.value)
        return yaml.safe_load(text)
    except yaml.YAMLError as error:
        mark = getattr(error, "problem_mark", None)
        recovered = {}
        for raw in text.splitlines():
            line = re.match(r"^([A-Za-z_][\w-]*):[ \t]*(\S.*)$", raw)
            if line and not line.group(2).startswith(("|", ">", "[", "{")):
                recovered[line.group(1)] = line.group(2).strip().strip("\"'")
        if recovered:
            warn(first_line + (mark.line if mark else 0), "the yaml had a formatting problem: only the simple fields were read")
            return recovered
        raise


def parse_batch(markdown: str) -> BatchPlan:
    """Read one short per section, repairing small mistakes instead of rejecting them; never return partial commits.

    The text goes to a writer that can infer a lot, so only a section with nothing readable is an error. Everything else
    that was fixed or ignored is reported in ``warnings``.
    """
    result = BatchPlan()
    markdown = markdown.lstrip("\ufeff")
    if len(markdown.encode("utf-8")) > 2_000_000:
        result.errors.append(BatchError(line=1, message="file exceeds 2 MB"))
        return result
    lines = markdown.replace("\r\n", "\n").replace("\r", "\n").splitlines()

    def warn(line: int, message: str) -> None:
        result.warnings.append(BatchError(line=max(1, line), message=message))

    for pattern in (r"^##\s+\S", r"^#{1,6}\s+\S"):
        headings = [i for i, line in enumerate(lines) if re.match(pattern, line)]
        if headings:
            break
    sections = [(h, headings[n + 1] if n + 1 < len(headings) else len(lines)) for n, h in enumerate(headings)]
    if not sections:
        sections = [(-1, len(lines))]  # no headings at all: the whole text is one short (or a list of them)
    taken: set[str] = set()
    for start, end in sections:
        heading = lines[start] if start >= 0 else ""
        body_start = start + 1
        found = _blocks(lines, body_start, end, warn)
        if not found:
            text = "\n".join(lines[body_start:end]) + "\n"
            if text.strip():
                found = [(body_start + 1, text)]
                if start >= 0:
                    warn(start + 1, "no yaml block: read the section text as yaml")
        if not found:
            result.errors.append(BatchError(line=max(1, start + 1), message="nothing to read in this section: add the short's fields"))
            continue
        merged: dict = {}
        shorts_raw: list[tuple[int, dict]] = []
        try:
            for first_line, text in found:
                loaded = _load(text, first_line, warn)
                if isinstance(loaded, list) and all(isinstance(item, dict) for item in loaded):
                    shorts_raw.extend((first_line, item) for item in loaded)
                elif isinstance(loaded, dict):
                    if merged:
                        warn(first_line, "a second yaml block was merged into the first")
                    merged.update(loaded)
                elif loaded is not None:
                    raise ValueError("the short must be a list of `field: value` lines")
        except yaml.YAMLError as error:
            mark = getattr(error, "problem_mark", None)
            result.errors.append(BatchError(line=found[0][0] + (mark.line if mark else 0), message="could not read this section as yaml: check the lines near here"))
            continue
        except ValueError as error:
            result.errors.append(BatchError(line=found[0][0], message=str(error)))
            continue
        if merged:
            shorts_raw.insert(0, (found[0][0], merged))
        if not shorts_raw:
            result.errors.append(BatchError(line=max(1, start + 1), message="nothing to read in this section: add the short's fields"))
            continue
        for line, raw in shorts_raw:
            try:
                data = _normalize(raw, heading, line, taken, warn)
                short = BatchShort.model_validate(data)
                taken.add(short.id)
                result.shorts.append(short)
            except ValidationError as error:
                for item in error.errors():
                    field = str(item["loc"][0]) if item["loc"] else "short"
                    result.errors.append(BatchError(line=line, message=f"{field}: {item['msg']}"))
            except (ValueError, RecursionError) as error:
                result.errors.append(BatchError(line=line, message=str(error)))
    return result
