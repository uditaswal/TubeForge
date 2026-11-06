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


def bound_candidate():
    import hashlib
    from tubeforge.domain.contracts import ContentPackage
    from tubeforge.providers.fake import FakeContentProvider

    plan_raw = candidate()
    plan = LongFormPlanningContract.model_validate(plan_raw)
    package = FakeContentProvider().generate_package(plan.request).model_dump(mode='json')
    for section, sid in zip(package['script_sections'], plan.section_ids, strict=True):
        section['section_id'] = sid
    package['metadata']['chapters'] = [dict(section_id=c.section_ids[0], label=c.title) for c in plan.chapters]
    package = ContentPackage.model_validate(package)
    packet = json.dumps({'schema_version': '1.1', 'sources': [s.model_dump(mode='json') for s in package.request.sources]}).encode()
    plan_raw['source_packet_sha256'] = hashlib.sha256(packet).hexdigest()
    return LongFormPlanningContract.model_validate(plan_raw), package.model_dump_json().encode(), packet


def test_package_binding_accepts_existing_gate_and_exact_sources():
    import hashlib
    from tubeforge.pipeline.long_form_contracts import validate_long_form_package
    plan, package, packet = bound_candidate()
    result = validate_long_form_package(plan, package, packet, accepted_script_identity=hashlib.sha256(package).hexdigest())
    assert tuple(s.section_id for s in result.script_sections) == plan.section_ids


@pytest.mark.parametrize('change', ['no_gate', 'stale_bytes', 'source_hash', 'brief', 'chapter', 'scene_order', 'sections', 'source_contents', 'reference_missing', 'reference_unbound'])
def test_package_binding_rejects_stale_or_conflicting_inputs(change):
    import hashlib
    from tubeforge.pipeline.long_form_contracts import validate_long_form_package
    plan, package, packet = bound_candidate()
    raw = json.loads(package)
    reference = None
    if change == 'brief': raw['request']['angle'] = 'A different angle'
    elif change == 'chapter': raw['metadata']['chapters'][0]['label'] = 'Conflicting title'
    elif change == 'scene_order': raw['scene_plans'].reverse()
    elif change == 'sections': raw['script_sections'].reverse()
    elif change == 'source_contents':
        altered = json.loads(packet)
        altered['sources'][0]['excerpt'] = 'Changed evidence'
        packet = json.dumps(altered).encode()
        plan = plan.model_copy(update={'source_packet_sha256': hashlib.sha256(packet).hexdigest()})
    elif change == 'reference_missing': plan = plan.model_copy(update={'reference_snapshot_sha256': '1' * 64})
    elif change == 'reference_unbound': reference = b'unbound reference'
    package = json.dumps(raw).encode()
    identity = hashlib.sha256(package).hexdigest()
    if change == 'no_gate': identity = None
    elif change == 'stale_bytes': package += b' '
    elif change == 'source_hash': packet += b' '
    with pytest.raises(ValueError):
        validate_long_form_package(plan, package, packet, accepted_script_identity=identity, reference_snapshot_bytes=reference)


def technical_probe():
    return dict(artifact_sha256='1'*64,width=1920,height=1080,fps=30,video_codec='h264',audio_codec='aac',sample_rate=48000,duration_seconds=600,integrated_lufs=-14,true_peak_dbtp=-2,full_decode_passed=True,chapter_starts_seconds=[0,200,400])


def test_final_probe_requires_matching_artifact_target_and_chapters():
    from tubeforge.domain.long_form import LongFormTechnicalProbe
    probe = LongFormTechnicalProbe.model_validate(technical_probe())
    plan = LongFormPlanningContract.model_validate(candidate())
    probe.validate_target(plan,artifact_sha256='1'*64)
    with pytest.raises(ValueError,match='different artifact'):
        probe.validate_target(plan,artifact_sha256='2'*64)
    longer_plan = plan.model_copy(update={'request': plan.request.model_copy(update={'target_duration_seconds':900})})
    with pytest.raises(ValueError,match='five percent'):
        probe.validate_target(longer_plan,artifact_sha256='1'*64)


@pytest.mark.parametrize('field,value', [
    ('width',1080), ('height',1920), ('duration_seconds',599), ('duration_seconds',901),
    ('integrated_lufs',-16), ('true_peak_dbtp',-1), ('true_peak_dbtp',float('nan')),
    ('full_decode_passed',False), ('chapter_starts_seconds',[1,200,400]),
    ('chapter_starts_seconds',[0,200,595]), ('chapter_starts_seconds',[0,400,200]),
    ('chapter_starts_seconds',[0,float('nan'),400]),
])
def test_final_probe_rejects_incompatible_or_missing_technical_evidence(field,value):
    from tubeforge.domain.long_form import LongFormTechnicalProbe
    raw = technical_probe()
    raw[field] = value
    with pytest.raises(ValidationError):
        LongFormTechnicalProbe.model_validate(raw)


def test_published_schemas_match_content_lane_interfaces():
    from tubeforge.domain.long_form import LongFormTechnicalProbe
    for model, name in [(LongFormPlanningContract,'planning_contract'), (LongFormTechnicalProbe,'technical_probe')]:
        stored = json.loads((FIXTURE.parent / f'{name}.schema.json').read_text())
        assert stored == model.model_json_schema()


def test_duration_tolerance_is_five_percent_including_boundary():
    from tubeforge.domain.long_form import LongFormTechnicalProbe
    plan = LongFormPlanningContract.model_validate(candidate())
    raw = technical_probe()
    raw['duration_seconds'] = 630
    LongFormTechnicalProbe.model_validate(raw).validate_target(plan,artifact_sha256='1'*64)
    raw['duration_seconds'] = 630.01
    with pytest.raises(ValueError,match='five percent'):
        LongFormTechnicalProbe.model_validate(raw).validate_target(plan,artifact_sha256='1'*64)
