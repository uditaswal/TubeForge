"""Check the script prompt size before a request is queued, and shorten source excerpts to fit.

The fixed writer instructions take about 57k characters, so a few long source pages can push the assembled
prompt past the ceiling. That used to fail inside the job, after it was queued. Here the request is measured
when it is built: long excerpts are trimmed (at a sentence end, longest first) to fit, or the brief is
refused with the real numbers. Excerpts are trimmed before they are hashed into the source packet, so the
packet still matches the exact text the writer sees.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from tubeforge.domain.contracts import ContentRequest
from tubeforge.providers.content.prompts import build_content_prompt

_SENTENCE_END = re.compile(r"[.!?][\"')\]]?\s")


class PromptTooLarge(ValueError):
    """The brief cannot fit in one script prompt even with every excerpt trimmed to its minimum."""


@dataclass(frozen=True)
class FitReport:
    max_chars: int
    prompt_before: int
    prompt_after: int
    trimmed: tuple[tuple[str, int, int], ...]   # (source_id, chars before, chars after)

    @property
    def changed(self) -> bool:
        return bool(self.trimmed)

    def summary(self) -> str:
        parts = ", ".join(f"{sid}: {before} to {after} characters" for sid, before, after in self.trimmed)
        return f"source excerpts shortened so the writer prompt fits ({self.prompt_before} to {self.prompt_after} of {self.max_chars} characters): {parts}"


def prompt_length(request: ContentRequest) -> int:
    return len(build_content_prompt(request, template_version=request.prompt_version, max_chars=10 ** 9))


def trim_text(text: str, limit: int) -> str:
    """Cut at a sentence end near ``limit`` (never mid-word), keeping at least 70% of the allowed length."""
    text = text.strip()
    if len(text) <= limit:
        return text
    head = text[:limit]
    ends = [m.end() for m in _SENTENCE_END.finditer(head)]
    if ends and ends[-1] >= limit * 0.7:
        return head[:ends[-1]].strip()
    return head.rsplit(" ", 1)[0].strip() if " " in head else head


def _with_cap(request: ContentRequest, cap: int) -> ContentRequest:
    sources = tuple(s.model_copy(update={"excerpt": trim_text(s.excerpt or "", cap)}) if s.excerpt and len(s.excerpt) > cap else s
                    for s in request.sources)
    return request.model_copy(update={"sources": sources})


def fit_request(request: ContentRequest, *, max_chars: int, min_per_source: int = 1_500, margin: int = 2_500,
                auto_trim: bool = True) -> tuple[ContentRequest, FitReport]:
    """Return a request whose assembled prompt fits ``max_chars - margin``; raise ``PromptTooLarge`` if it cannot."""
    allowed = max_chars - margin
    before = prompt_length(request)
    if before <= allowed:
        return request, FitReport(max_chars, before, before, ())
    longest = max((len(s.excerpt or "") for s in request.sources), default=0)
    if not auto_trim or longest <= min_per_source:
        raise PromptTooLarge(_message(request, before, allowed, max_chars, auto_trim))
    floor = _with_cap(request, min_per_source)
    if prompt_length(floor) > allowed:
        raise PromptTooLarge(_message(request, before, allowed, max_chars, auto_trim, floor=prompt_length(floor)))
    low, high = min_per_source, longest          # largest uniform cap that still fits; short sources keep all their text
    while low < high:
        middle = (low + high + 1) // 2
        if prompt_length(_with_cap(request, middle)) <= allowed:
            low = middle
        else:
            high = middle - 1
    fitted = _with_cap(request, low)
    trimmed = tuple((o.source_id, len(o.excerpt or ""), len(n.excerpt or ""))
                    for o, n in zip(request.sources, fitted.sources) if len(o.excerpt or "") != len(n.excerpt or ""))
    return fitted, FitReport(max_chars, before, prompt_length(fitted), trimmed)


def _message(request: ContentRequest, before: int, allowed: int, max_chars: int, auto_trim: bool, *, floor: int | None = None) -> str:
    sizes = ", ".join(f"{s.source_id}: {len(s.excerpt or '')}" for s in request.sources) or "none"
    if floor is not None:
        return (f"The brief is too large for one script prompt even with every source excerpt cut to its minimum: "
                f"{floor} characters against {allowed} allowed ({max_chars} limit). Use fewer or shorter sources. Excerpt sizes: {sizes}.")
    reason = "Trimming is turned off in Settings; " if not auto_trim else ""
    return (f"{reason}the brief is too large for one script prompt: {before} characters against {allowed} allowed "
            f"({max_chars} limit). Use fewer or shorter sources. Excerpt sizes: {sizes}.")
