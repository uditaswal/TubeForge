"""Pure checkpoint transformations; durable job ownership remains the caller's."""
from __future__ import annotations

from decimal import Decimal

from tubeforge.domain.long_form import LongFormPlanningContract
from tubeforge.domain.reference_video import ReferenceSnapshot
from tubeforge.domain.long_form_budget import LongFormCallLedger, ObservedUsage, StageCall, Stage


def reserve_stage_call(ledger: LongFormCallLedger, stage: Stage, *, brief_sha256: str) -> LongFormCallLedger:
    """Reserve once before launch; failed/unknown calls are never refunded.

    The caller must atomically persist the returned checkpoint under its existing
    job lease before invoking a provider. This pure helper is not a durable lock.
    """
    if ledger.brief_sha256 != brief_sha256:
        raise ValueError('budget belongs to a different exact brief')
    if any(c.state == 'pending' for c in ledger.calls):
        raise ValueError('inspect the pending call before reserving another')
    raw = ledger.model_dump(mode='python')
    raw['calls'] = (*ledger.calls, dict(call_id=f'call-{len(ledger.calls)+1}',stage=stage))
    return LongFormCallLedger.model_validate(raw)


def finish_stage_call(ledger: LongFormCallLedger, call_id: str, *, succeeded: bool,
                      invocation_started: bool | None, usage: ObservedUsage | None = None,
                      narration_changed: bool = False) -> LongFormCallLedger:
    matches = [c for c in ledger.calls if c.call_id == call_id]
    if not matches or matches[0].state != 'pending':
        raise ValueError('only an existing pending call can be finalized')
    call = matches[0]
    if narration_changed and call.stage not in {'draft','repair'}:
        raise ValueError('auxiliary stages cannot rewrite narration')
    result = StageCall(call_id=call_id, stage=call.stage, state='succeeded' if succeeded else 'failed',
                       invocation_started=invocation_started, usage=usage)
    raw = ledger.model_dump(mode='python')
    raw['calls'] = tuple(result if c.call_id == call_id else c for c in ledger.calls)
    return LongFormCallLedger.model_validate(raw)


def summarize_usage(ledger: LongFormCallLedger) -> dict:
    """Keep observed subtotals separate from unknown totals, even on failures."""
    summary = {}
    for field in ObservedUsage.model_fields:
        values = []
        for call in ledger.calls:
            if call.state != 'pending' and call.invocation_started is False:
                values.append(Decimal(0) if field == 'reported_cost_usd' else 0)
            else:
                values.append(getattr(call.usage,field) if call.usage is not None else None)
        known = [v for v in values if v is not None]
        complete = bool(values) and len(known) == len(values)
        subtotal = sum(known, Decimal(0) if field == 'reported_cost_usd' else 0)
        summary[field] = dict(known_subtotal=subtotal,total=subtotal if complete else None,complete=complete)
    summary['reserved_calls'] = len(ledger.calls)
    summary['narration_attempts'] = sum(c.stage in {'draft','repair'} for c in ledger.calls)
    summary['subscription_fraction'] = None
    return summary


def long_form_brief_identity(planning: LongFormPlanningContract, *, reference: ReferenceSnapshot | None = None) -> str:
    """Semantic allowance key; render/provider changes cannot reset attempts.

    Exact source/reference byte integrity is checked separately. Capture times,
    derived hashes and provider routing must not create a fresh writer allowance.
    """
    import hashlib
    import json
    from tubeforge.domain.contracts import generation_request_key_payload
    from tubeforge.pipeline.long_form_reference import reference_content_identity

    if (reference is None) != (planning.reference_snapshot_sha256 is None):
        raise ValueError('brief identity requires its bound reference content')
    request = generation_request_key_payload(planning.request)
    for field in ('script_owner','script_model','script_routing_mode'):
        request.pop(field,None)
    for source in request['sources']:
        source.pop('retrieved_at',None)
        source.pop('content_sha256',None)
    material = dict(request=request,reference_content_sha256=reference_content_identity(reference) if reference is not None else None)
    return hashlib.sha256(json.dumps(material,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
