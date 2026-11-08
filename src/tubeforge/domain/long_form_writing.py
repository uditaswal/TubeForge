"""Single-invocation LF2 contracts; hashes bind context, never approval."""
from __future__ import annotations

from typing import Literal
from pydantic import Field,model_validator
from tubeforge.domain.contracts import ContentPackage,ContentRequest,DomainModel
from tubeforge.domain.long_form import LongFormChapter


PROFILE='m6-content-long-v1'


class ReferenceExcerpt(DomainModel):
    cue_index:int=Field(ge=0,le=9999)
    start_seconds:float=Field(ge=0,allow_inf_nan=False)
    text:str=Field(min_length=1,max_length=500)


class ReferenceImprovement(DomainModel):
    reference_cue_index:int=Field(ge=0,le=9999)
    reference_quote:str=Field(min_length=1,max_length=500)
    observation:str=Field(min_length=1,max_length=500)
    viewer_problem_hypothesis:str=Field(min_length=1,max_length=500)
    original_addition:str=Field(min_length=1,max_length=700)
    source_ids:tuple[str,...]=Field(min_length=1,max_length=5)
    section_ids:tuple[str,...]=Field(min_length=1,max_length=20)


class LongFormDraftResult(DomainModel):
    status:Literal['ready','insufficient_sources']
    package:ContentPackage|None
    chapters:tuple[LongFormChapter,...]=Field(max_length=12)
    improvements:tuple[ReferenceImprovement,...]=Field(max_length=3)
    reason:str|None=Field(max_length=1000)

    @model_validator(mode='after')
    def consistent_result(self):
        if self.status=='insufficient_sources':
            if self.package is not None or self.chapters or self.improvements or not self.reason or not self.reason.strip():
                raise ValueError('insufficient_sources requires only a concrete reason')
            return self
        if self.package is None or self.reason is not None or len(self.chapters)<3 or len(self.improvements)<2:
            raise ValueError('ready draft requires package, chapters and two or three supported original additions')
        request=self.package.request
        if request.prompt_version!=PROFILE or request.aspect_ratio!='16:9' or not 600<=request.target_duration_seconds<=900 or request.production_mode!='generated':
            raise ValueError('long-form writing requires the explicit 600–900-second landscape profile')
        sections=tuple(s.section_id for s in self.package.script_sections)
        if not 3<=len(sections)<=100 or tuple(s for c in self.chapters for s in c.section_ids)!=sections:
            raise ValueError('chapters must cover every canonical section exactly once in order')
        if len({c.chapter_id for c in self.chapters})!=len(self.chapters):
            raise ValueError('chapter IDs must be unique')
        expected=tuple((c.section_ids[0],c.title) for c in self.chapters)
        if tuple((c.section_id,c.label) for c in self.package.metadata.chapters)!=expected:
            raise ValueError('package chapter labels must match the companion groups')
        source_ids={s.source_id for s in request.sources}
        if len({i.original_addition.casefold().strip() for i in self.improvements})!=len(self.improvements):
            raise ValueError('original additions must be distinct')
        for improvement in self.improvements:
            if not set(improvement.source_ids)<=source_ids or not set(improvement.section_ids)<=set(sections):
                raise ValueError('original additions must resolve to actual sources and sections')
        return self


class ClaimEvidenceCheck(DomainModel):
    claim_id:str=Field(min_length=1,max_length=64)
    source_id:str=Field(min_length=1,max_length=64)
    source_quote:str=Field(min_length=15,max_length=500)
    verdict:Literal['supported','qualify','unsupported']
    reason:str=Field(min_length=1,max_length=700)


class EditorialFinding(DomainModel):
    severity:Literal['blocker','advisory']
    category:Literal['grounding','originality','hook','structure','clarity','payoff','packaging','length']
    section_ids:tuple[str,...]=Field(max_length=20)
    detail:str=Field(min_length=1,max_length=1000)


class LongFormReviewResult(DomainModel):
    decision:Literal['pass','repair','insufficient_sources']
    claim_checks:tuple[ClaimEvidenceCheck,...]=Field(min_length=1,max_length=500)
    findings:tuple[EditorialFinding,...]=Field(max_length=40)
    originality_rationale:str=Field(min_length=1,max_length=2000)
    promise_payoff_rationale:str=Field(min_length=1,max_length=1500)

    @model_validator(mode='after')
    def truthful_decision(self):
        blockers=any(f.severity=='blocker' for f in self.findings)
        unsupported=any(c.verdict!='supported' for c in self.claim_checks)
        if self.decision=='pass' and (blockers or unsupported):
            raise ValueError('review cannot pass unresolved grounding or editorial blockers')
        if self.decision!='pass' and not blockers and not unsupported:
            raise ValueError('rejection must identify a concrete unresolved defect')
        return self


class LongFormTokenPolicy(DomainModel):
    maximum_input_tokens:int=Field(default=30000,ge=1000,le=30000)
    maximum_output_tokens:int=Field(default=16000,ge=1000,le=20000)
    total_reserved_tokens:int=Field(default=150000,ge=2000,le=250000)
    maximum_calls:Literal[5]=5
    maximum_narration_attempts:int=Field(default=2,ge=1,le=2)


class LongFormHostRequest(DomainModel):
    """Path-free one-call operations; no arbitrary prompt, command or credentials."""
    operation:Literal['PreflightLongFormV1','PrepareLongFormCallV1','LongFormStageV1','InspectLongFormCallV1']
    stage:Literal['research','draft','review','repair']
    call_id:str=Field(pattern=r'^lf2-[a-f0-9]{32}-call-[1-5]$')
    brief_sha256:str=Field(pattern=r'^[a-f0-9]{64}$')
    resolved_model:str|None=Field(default=None,min_length=1,max_length=100)
    request:ContentRequest
    reference_snapshot_sha256:str=Field(pattern=r'^[a-f0-9]{64}$')
    reference_content_sha256:str=Field(pattern=r'^[a-f0-9]{64}$')
    reference_excerpts:tuple[ReferenceExcerpt,...]=Field(min_length=1,max_length=12)
    source_packet_sha256:str|None=Field(default=None,pattern=r'^[a-f0-9]{64}$')
    draft:LongFormDraftResult|None=None
    review:LongFormReviewResult|None=None
    rejected_output:str|None=Field(default=None,max_length=60000)
    local_rejection:tuple[str,...]=Field(default=(),max_length=20)
    originality_context:str=Field(default='',max_length=6000)
    research_assessment:str=Field(default='',max_length=2000)
    token_policy:LongFormTokenPolicy=Field(default_factory=LongFormTokenPolicy)

    @model_validator(mode='before')
    @classmethod
    def bind_wire_request(cls,value):
        if isinstance(value,dict) and isinstance(value.get('draft'),dict) and isinstance(value['draft'].get('package'),dict):
            draft=dict(value['draft']);package=dict(draft['package'])
            if 'request' not in package:
                package['request']=value.get('request');draft['package']=package;value={**value,'draft':draft}
        return value

    @model_validator(mode='after')
    def bind_stage(self):
        request=self.request
        if request.prompt_version!=PROFILE or request.aspect_ratio!='16:9' or not 600<=request.target_duration_seconds<=900 or request.production_mode!='generated':
            raise ValueError('LF2 operation requires the explicit long-form profile')
        if self.stage!='research' and self.source_packet_sha256 is None:
            raise ValueError('writing/review requires a captured primary-source packet')
        if any(not r.strip() or len(r)>1000 for r in self.local_rejection):
            raise ValueError('local rejection reasons must be bounded and nonblank')
        if self.stage in {'research','draft'} and (self.draft is not None or self.review is not None or self.rejected_output is not None or self.local_rejection):
            raise ValueError('initial stages cannot carry a hidden draft or review')
        if self.stage=='review' or (self.stage=='repair' and self.rejected_output is None):
            if self.draft is None or self.draft.status!='ready' or self.draft.package is None:
                raise ValueError('review/repair requires an exact validated draft')
            if self.draft.package.request!=request:
                raise ValueError('draft input packet differs from trusted request')
        if self.stage=='review' and (self.review is not None or self.rejected_output is not None or self.local_rejection):
            raise ValueError('independent review must not receive a model-authored prior verdict')
        if self.stage=='repair':
            if self.rejected_output is not None:
                if not self.rejected_output.strip() or not self.local_rejection or self.draft is not None or self.review is not None:
                    raise ValueError('raw repair requires only the rejected output and explicit local validation errors')
            elif self.review is None or self.review.decision=='pass' or self.local_rejection:
                raise ValueError('repair requires explicit rejected findings')
        if len({e.cue_index for e in self.reference_excerpts})!=len(self.reference_excerpts):
            raise ValueError('reference excerpt indexes must be distinct')
        return self
