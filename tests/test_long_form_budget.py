from decimal import Decimal

from pydantic import ValidationError
import pytest

from tubeforge.domain.long_form_budget import LongFormCallLedger,ObservedUsage
from tubeforge.pipeline.long_form_budget import reserve_stage_call, finish_stage_call, summarize_usage

BRIEF='a'*64


def reserve(ledger,stage): return reserve_stage_call(ledger,stage,brief_sha256=BRIEF)


def finish(ledger,**overrides):
    args=dict(succeeded=True,invocation_started=True)
    args.update(overrides)
    return finish_stage_call(ledger,ledger.calls[-1].call_id,**args)


def test_budget_roundtrip_preserves_rejected_attempts_and_stops_duplicate_stages():
    ledger=LongFormCallLedger(brief_sha256=BRIEF,research_required=True)
    with pytest.raises(ValidationError,match='research'): reserve(ledger,'draft')
    ledger=finish(reserve(ledger,'research'))
    ledger=finish(reserve(ledger,'draft'),succeeded=False)
    ledger=LongFormCallLedger.model_validate_json(ledger.model_dump_json())
    ledger=finish(reserve(ledger,'repair'),narration_changed=True)
    ledger=finish(reserve(ledger,'review'))
    ledger=finish(reserve(ledger,'storyboard'))
    assert len(ledger.calls)==5
    assert summarize_usage(ledger)['narration_attempts']==2
    with pytest.raises(ValidationError): reserve(ledger,'repair')
    with pytest.raises(ValidationError): reserve(ledger,'research')


def test_pending_or_wrong_brief_cannot_launch_another_call():
    ledger=reserve(LongFormCallLedger(brief_sha256=BRIEF),'draft')
    with pytest.raises(ValueError,match='pending'): reserve(ledger,'review')
    with pytest.raises(ValueError,match='different exact brief'):
        reserve_stage_call(ledger,'review',brief_sha256='b'*64)
    with pytest.raises(ValueError): finish_stage_call(ledger,'call-5',succeeded=False,invocation_started=False)


def test_auxiliary_rewrite_is_rejected_without_mutating_checkpoint():
    ledger=reserve(LongFormCallLedger(brief_sha256=BRIEF),'review')
    with pytest.raises(ValueError,match='rewrite'): finish(ledger,narration_changed=True)
    assert ledger.calls[0].state=='pending'
    finished=finish(ledger)
    with pytest.raises(ValueError,match='pending'): finish_stage_call(finished,'call-1',succeeded=True,invocation_started=True)


def test_failed_or_unstarted_calls_do_not_refund_a_stage():
    ledger=finish(reserve(LongFormCallLedger(brief_sha256=BRIEF),'draft'),succeeded=False,invocation_started=False)
    with pytest.raises(ValidationError): reserve(ledger,'draft')
    assert summarize_usage(ledger)['input_tokens']['total']==0
    assert ledger.calls[0].state=='failed'


def test_repair_requires_finished_draft_and_records_cannot_erase_call_order():
    with pytest.raises(ValidationError): reserve(LongFormCallLedger(brief_sha256=BRIEF),'repair')
    with pytest.raises(ValidationError): LongFormCallLedger(brief_sha256=BRIEF,calls=[dict(call_id='call-2',stage='draft')])


def test_missing_or_mixed_usage_stays_explicitly_incomplete():
    ledger=LongFormCallLedger(brief_sha256=BRIEF)
    assert summarize_usage(ledger)['input_tokens']['total'] is None
    ledger=finish(reserve(ledger,'draft'),usage=ObservedUsage(input_tokens=100,output_tokens=20,reported_cost_usd=Decimal('0.15')))
    ledger=finish(reserve(ledger,'review'),usage=ObservedUsage(output_tokens=10))
    summary=summarize_usage(ledger)
    assert summary['input_tokens']==dict(known_subtotal=100,total=None,complete=False)
    assert summary['output_tokens']==dict(known_subtotal=30,total=30,complete=True)
    assert summary['reported_cost_usd']['total'] is None
    assert summary['reported_cost_usd']['known_subtotal']==Decimal('0.15')
    assert summary['reasoning_tokens']['total'] is None
    assert summary['subscription_fraction'] is None


def test_started_failure_usage_is_retained_but_unknown_usage_is_not_zero():
    ledger=finish(reserve(LongFormCallLedger(brief_sha256=BRIEF),'draft'),succeeded=False,
                  usage=ObservedUsage(input_tokens=42,reported_cost_usd='0.10'))
    assert summarize_usage(ledger)['input_tokens']['total']==42
    ledger=finish(reserve(ledger,'repair'),succeeded=False,invocation_started=None)
    assert summarize_usage(ledger)['input_tokens']['total'] is None
    assert summarize_usage(ledger)['input_tokens']['known_subtotal']==42


@pytest.mark.parametrize('field,value',[('input_tokens',-1),('output_tokens',1.5),('reasoning_tokens',True),('reported_cost_usd','NaN')])
def test_invalid_usage_is_rejected(field,value):
    with pytest.raises(ValidationError): ObservedUsage.model_validate({field:value})


def test_budget_schema_fixture_and_checkpoint_round_trip():
    import json
    from pathlib import Path
    assert json.loads((Path(__file__).parent/'fixtures/long_form/LongFormCallLedger.schema.json').read_text()) == LongFormCallLedger.model_json_schema()
    ledger=reserve(LongFormCallLedger(brief_sha256=BRIEF),'draft')
    assert LongFormCallLedger.model_validate_json(ledger.model_dump_json())==ledger
