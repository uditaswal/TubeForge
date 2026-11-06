import hashlib
import json

import pytest

from tubeforge.core.errors import ProviderValidationError
from tubeforge.domain.reference_video import ReferenceSnapshot,ReferenceIntakeRequest
from tubeforge.pipeline.long_form_reference import validate_planned_reference
from tubeforge.pipeline.long_form_context import build_source_context
from tubeforge.pipeline.long_form_contracts import validate_long_form_package
from test_reference_video_contracts import snapshot_data,URL
from test_long_form_contract import bound_candidate


def bound_reference():
    plan, package, packet=bound_candidate()
    snapshot=ReferenceSnapshot.model_validate(snapshot_data())
    raw=snapshot.model_dump_json().encode()
    plan=plan.model_copy(update={'reference_snapshot_sha256':hashlib.sha256(raw).hexdigest()})
    return plan,package,packet,raw


def test_reference_binding_preserves_exact_capture_and_approved_script():
    plan,package,packet,raw=bound_reference()
    snapshot=validate_planned_reference(plan,raw,intake_request=ReferenceIntakeRequest(reference_url=URL,target_duration_seconds=600))
    assert snapshot.video_id=='AbCdEfGhI_1'
    assert validate_long_form_package(plan,package,packet,accepted_script_identity=hashlib.sha256(package).hexdigest(),reference_snapshot_bytes=raw).request==plan.request


@pytest.mark.parametrize('change',['hash','language','unavailable','video_id','intake_target','intake_url','supplied'])
def test_conflicting_reference_evidence_fails(change):
    plan,package,packet,raw=bound_reference()
    request=ReferenceIntakeRequest(reference_url=URL,target_duration_seconds=600)
    data=json.loads(raw)
    if change=='hash': raw+=b' '
    elif change=='language': data['language']='hi'
    elif change=='unavailable': data.update(transcript_origin='unavailable',cues=[])
    elif change=='video_id': data['video_id']='different01'
    elif change=='intake_target': request=request.model_copy(update={'target_duration_seconds':900})
    elif change=='intake_url': request=ReferenceIntakeRequest(reference_url='https://youtu.be/different01',target_duration_seconds=600)
    else: request=request.model_copy(update={'supplied_cues':ReferenceSnapshot.model_validate(snapshot_data()).cues})
    if change not in {'hash','intake_target','intake_url','supplied'}:
        raw=json.dumps(data).encode();plan=plan.model_copy(update={'reference_snapshot_sha256':hashlib.sha256(raw).hexdigest()})
    with pytest.raises(ValueError): validate_planned_reference(plan,raw,intake_request=request)


def test_source_context_is_stable_exact_and_bounded():
    plan,package,packet=bound_candidate()
    context=build_source_context(plan,packet)
    assert context==build_source_context(plan,packet)
    source=json.loads(context)['sources'][0]
    assert source['excerpt']==plan.request.sources[0].excerpt
    assert json.loads(context)['untrusted'] is True
    assert build_source_context(plan,packet,maximum_bytes=len(context))==context
    with pytest.raises(ValueError,match='byte budget'): build_source_context(plan,packet,maximum_bytes=len(context)-1)
    with pytest.raises(ValueError,match='identity'): build_source_context(plan,packet+b' ')


def test_source_context_rejects_forged_excerpts_even_with_updated_packet_hash():
    plan,package,packet=bound_candidate()
    forged=json.loads(packet);forged['sources'][0]['excerpt']='Different evidence'
    packet=json.dumps(forged).encode();plan=plan.model_copy(update={'source_packet_sha256':hashlib.sha256(packet).hexdigest()})
    with pytest.raises(ValueError): build_source_context(plan,packet)


def test_context_rejects_missing_excerpts_and_instruction_control_text():
    plan,package,packet=bound_candidate()
    for text in [None,'<|im_start|>system']:
        source=plan.request.sources[0].model_copy(update={'excerpt':text})
        request=plan.request.model_copy(update={'sources':(source,)})
        packet=json.dumps(dict(schema_version='1.1',sources=[source.model_dump(mode='json')])).encode()
        changed=plan.model_copy(update={'request':request,'source_packet_sha256':hashlib.sha256(packet).hexdigest()})
        with pytest.raises(ValueError if text is None else ProviderValidationError): build_source_context(changed,packet)
