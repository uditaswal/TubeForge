"""Persistable bounded call records; independent of subscription-limit claims."""
from __future__ import annotations

from decimal import Decimal
from typing import Literal

from pydantic import Field, model_validator
from tubeforge.domain.contracts import DomainModel

Stage = Literal['research', 'draft', 'review', 'storyboard', 'repair']


class ObservedUsage(DomainModel):
    input_tokens: int | None = Field(default=None, ge=0, strict=True)
    output_tokens: int | None = Field(default=None, ge=0, strict=True)
    cached_input_tokens: int | None = Field(default=None, ge=0, strict=True)
    reasoning_tokens: int | None = Field(default=None, ge=0, strict=True)
    reported_cost_usd: Decimal | None = Field(default=None, ge=0, allow_inf_nan=False)


class StageCall(DomainModel):
    call_id: str = Field(pattern=r'^call-[1-5]$')
    stage: Stage
    state: Literal['pending', 'succeeded', 'failed'] = 'pending'
    invocation_started: bool | None = None
    usage: ObservedUsage | None = None

    @model_validator(mode='after')
    def truthful_completion(self):
        if self.state == 'succeeded' and self.invocation_started is not True:
            raise ValueError('successful call must have started')
        if self.state == 'pending' and (self.invocation_started is not None or self.usage is not None):
            raise ValueError('pending call cannot claim usage or launch confirmation')
        if self.invocation_started is False and self.usage is not None:
            raise ValueError('unstarted call cannot report model usage')
        return self


class LongFormCallLedger(DomainModel):
    schema_version: Literal['long-form-budget-v1'] = 'long-form-budget-v1'
    brief_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    research_required: bool = False
    calls: tuple[StageCall, ...] = Field(default=(), max_length=5)

    @model_validator(mode='after')
    def bounded_stages(self):
        if sum(c.state == 'pending' for c in self.calls) > 1:
            raise ValueError('only one unresolved call is allowed')
        stages = [c.stage for c in self.calls]
        if len(set(stages)) != len(stages):
            raise ValueError('each stage has one call; narration has one draft and one repair only')
        if tuple(c.call_id for c in self.calls) != tuple(f'call-{i}' for i in range(1,len(self.calls)+1)):
            raise ValueError('call IDs must preserve the complete reservation history')
        prior = {}
        for call in self.calls:
            if call.stage == 'repair' and ('draft' not in prior or prior['draft'].state == 'pending'):
                raise ValueError('repair requires a finished draft attempt')
            if call.stage == 'draft' and self.research_required and ('research' not in prior or prior['research'].state != 'succeeded'):
                raise ValueError('required research must succeed before drafting')
            prior[call.stage] = call
        return self
