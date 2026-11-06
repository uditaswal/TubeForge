"""LF0 interface acceptance: no provider calls or production registration."""
import copy
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from tubeforge.domain.long_form import LongFormPlanningContract

FIXTURE = Path(__file__).parent / 'fixtures' / 'long_form' / 'planning_contract.json'


def candidate():
    return json.loads(FIXTURE.read_text())


@pytest.mark.parametrize('seconds', [600, 720, 900])
def test_long_form_targets_round_trip_without_changing_brief(seconds):
    raw = candidate()
    raw['request']['target_duration_seconds'] = seconds
    value = LongFormPlanningContract.model_validate(raw)
    assert value.request.target_duration_seconds == seconds
    assert LongFormPlanningContract.model_validate_json(value.model_dump_json()) == value


@pytest.mark.parametrize('field,value', [
    ('target_duration_seconds', 599), ('target_duration_seconds', 901),
    ('aspect_ratio', '9:16'), ('prompt_version', 'm6-content-v7'),
])
def test_wrong_profile_is_rejected(field, value):
    raw = candidate()
    raw['request'][field] = value
    with pytest.raises(ValidationError):
        LongFormPlanningContract.model_validate(raw)


@pytest.mark.parametrize('change', ['unknown_source', 'duplicate_source', 'reorder', 'omit', 'duplicate_chapter', 'bad_hash'])
def test_evidence_and_chapter_binding_reject_invalid_inventory(change):
    raw = copy.deepcopy(candidate())
    if change == 'unknown_source': raw['cited_source_ids'] = ['missing']
    elif change == 'duplicate_source': raw['cited_source_ids'] *= 2
    elif change == 'reorder': raw['chapters'].reverse()
    elif change == 'omit': raw['chapters'][-1]['section_ids'] = ['missing-section']
    elif change == 'duplicate_chapter': raw['chapters'][-1]['chapter_id'] = raw['chapters'][0]['chapter_id']
    else: raw['source_packet_sha256'] = 'not-a-hash'
    with pytest.raises(ValidationError):
        LongFormPlanningContract.model_validate(raw)


def test_planning_contract_is_strict_and_does_not_claim_approval():
    raw = candidate()
    raw['approved'] = True
    with pytest.raises(ValidationError):
        LongFormPlanningContract.model_validate(raw)
