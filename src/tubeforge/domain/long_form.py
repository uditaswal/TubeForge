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


class LongFormTechnicalProbe(DomainModel):
    """Final-master measurement contract, not an approval or creative verdict.

    The media adapter must supply real encoded-file measurements. This model
    cannot establish that a probe/decode/listening operation actually ran.
    """

    artifact_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    width: Literal[1920]
    height: Literal[1080]
    fps: Literal[30]
    video_codec: Literal["h264"]
    audio_codec: Literal["aac"]
    sample_rate: Literal[48000]
    duration_seconds: float = Field(ge=600, le=900, allow_inf_nan=False)
    integrated_lufs: float = Field(ge=-15, le=-13, allow_inf_nan=False)
    true_peak_dbtp: float = Field(le=-1.5, allow_inf_nan=False)
    full_decode_passed: Literal[True]
    chapter_starts_seconds: tuple[float, ...] = Field(min_length=3, max_length=12)

    @model_validator(mode="after")
    def chapter_intervals(self) -> LongFormTechnicalProbe:
        import math

        starts = self.chapter_starts_seconds
        if starts[0] != 0 or any(not math.isfinite(s) for s in starts):
            raise ValueError("chapters must start at zero with finite timestamps")
        ends = (*starts[1:], self.duration_seconds)
        if any(end - start < 10 for start, end in zip(starts, ends, strict=True)):
            raise ValueError("every chapter must last at least ten seconds")
        return self

    def validate_target(self, planning: LongFormPlanningContract, *, artifact_sha256: str) -> None:
        if artifact_sha256 != self.artifact_sha256:
            raise ValueError("long-form technical probe belongs to a different artifact")
        if abs(self.duration_seconds - planning.request.target_duration_seconds) > planning.request.target_duration_seconds * 0.05:
            raise ValueError("long-form duration differs from target by more than five percent")
        if len(self.chapter_starts_seconds) != len(planning.chapters):
            raise ValueError("measured chapter count differs from accepted plan")


class MeasuredSectionTiming(DomainModel):
    section_id: str = Field(pattern=r'^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$')
    start_seconds: float = Field(ge=0, allow_inf_nan=False)
    end_seconds: float = Field(gt=0, allow_inf_nan=False)

    @model_validator(mode='after')
    def positive_span(self):
        if self.end_seconds <= self.start_seconds:
            raise ValueError('measured section must have positive duration')
        return self


class LongFormTimingManifest(DomainModel):
    schema_version: Literal['long-form-timing-v1'] = 'long-form-timing-v1'
    package_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    audio_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    artifact_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    timing_method: Literal['forced_alignment', 'measured_scene_audio']
    duration_seconds: float = Field(ge=600, le=900, allow_inf_nan=False)
    sections: tuple[MeasuredSectionTiming, ...] = Field(min_length=3, max_length=100)

    @model_validator(mode='after')
    def ordered_measured_spans(self):
        if len({s.section_id for s in self.sections}) != len(self.sections):
            raise ValueError('measured section IDs must be unique')
        previous_end = 0.0
        for section in self.sections:
            if section.start_seconds < previous_end or section.end_seconds > self.duration_seconds:
                raise ValueError('measured sections must be ordered, non-overlapping and inside final duration')
            previous_end = section.end_seconds
        return self
