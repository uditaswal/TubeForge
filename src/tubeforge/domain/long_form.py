"""Opt-in long-form planning contracts; not registered as a production preset.

The existing ContentRequest remains the canonical brief. This companion binds
chapter membership and evidence identities without adding a second video plan.
"""
from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from tubeforge.domain.contracts import ContentRequest, DomainModel


class LongFormChapter(DomainModel):
    chapter_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
    title: str = Field(min_length=1, max_length=120)
    section_ids: tuple[str, ...] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def unique_sections(self) -> LongFormChapter:
        if not self.title.strip() or any(not item.strip() for item in self.section_ids):
            raise ValueError("chapter title and section IDs must be nonblank")
        if len(set(self.section_ids)) != len(self.section_ids):
            raise ValueError("chapter section IDs must be unique")
        return self


class LongFormPlanningContract(DomainModel):
    """Pre-render interface; hashes are bindings, never approval assertions.

    Source IDs must resolve to the canonical request. Chapter section IDs cover
    the exact ordered section inventory once. Actual audio timestamps are added
    by later media stages, not invented by this planning contract.
    """

    schema_version: Literal["long-form-planning-v1"] = "long-form-planning-v1"
    request: ContentRequest
    source_packet_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    reference_snapshot_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    section_ids: tuple[str, ...] = Field(min_length=3, max_length=100)
    cited_source_ids: tuple[str, ...] = Field(min_length=1, max_length=100)
    chapters: tuple[LongFormChapter, ...] = Field(min_length=3, max_length=12)

    @model_validator(mode="after")
    def bind_profile_and_inventory(self) -> LongFormPlanningContract:
        request = self.request
        if request.prompt_version != "m6-content-long-v1":
            raise ValueError("long-form planning requires m6-content-long-v1")
        if request.aspect_ratio != "16:9" or not 600 <= request.target_duration_seconds <= 900:
            raise ValueError("long-form planning requires 16:9 and 600–900 seconds")
        if request.production_mode != "generated":
            raise ValueError("long-form planning requires original generated content")
        if len(set(self.section_ids)) != len(self.section_ids) or any(not s.strip() for s in self.section_ids):
            raise ValueError("section inventory must contain unique nonblank IDs")
        if len({c.chapter_id for c in self.chapters}) != len(self.chapters):
            raise ValueError("chapter IDs must be unique")
        flattened = tuple(s for c in self.chapters for s in c.section_ids)
        if flattened != self.section_ids:
            raise ValueError("chapters must cover every section exactly once in order")
        if len(set(self.cited_source_ids)) != len(self.cited_source_ids):
            raise ValueError("cited source IDs must be unique")
        if not set(self.cited_source_ids) <= {s.source_id for s in request.sources}:
            raise ValueError("cited source IDs must resolve to the canonical request")
        return self
