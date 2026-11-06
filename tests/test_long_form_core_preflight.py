"""C10 synthetic 60-scene, 15-minute contract smoke; no writer/media approval."""
import hashlib
import json

import pytest

from tubeforge.domain.long_form import LongFormPlanningContract, LongFormTimingManifest
from tubeforge.domain.long_form_budget import LongFormCallLedger, ObservedUsage
from tubeforge.domain.reference_video import ReferenceIntakeRequest, ReferenceSnapshot
from tubeforge.pipeline.long_form_budget import long_form_brief_identity, reserve_stage_call, finish_stage_call
from tubeforge.pipeline.long_form_preflight import audit_reference_package
from test_long_form_envelopes import representative_package
from test_reference_video_contracts import snapshot_data,URL


def smoke_inputs():
    request,package=representative_package()
    packet=json.dumps(dict(schema_version='1.1',sources=[s.model_dump(mode='json') for s in request.sources])).encode()
    snapshot=ReferenceSnapshot.model_validate(snapshot_data()); snapshot_bytes=snapshot.model_dump_json().encode()
    plan=LongFormPlanningContract(request=request,source_packet_sha256=hashlib.sha256(packet).hexdigest(),
        reference_snapshot_sha256=hashlib.sha256(snapshot_bytes).hexdigest(),
        section_ids=tuple(s.section_id for s in package.script_sections),cited_source_ids=('fixture',),
        chapters=[dict(chapter_id=f'chapter-{i//10}',title=f'Chapter {i//10+1}',section_ids=[s.section_id for s in package.script_sections[i:i+10]]) for i in range(0,60,10)])
    package_bytes=package.model_dump_json().encode();identity=hashlib.sha256(package_bytes).hexdigest()
    brief_identity=long_form_brief_identity(plan,reference=snapshot)
    ledger=LongFormCallLedger(brief_sha256=brief_identity,research_required=True)
    for stage in ['research','draft','review','storyboard']:
        ledger=reserve_stage_call(ledger,stage,brief_sha256=brief_identity)
        ledger=finish_stage_call(ledger,ledger.calls[-1].call_id,succeeded=True,invocation_started=True,
                                 usage=ObservedUsage(input_tokens=100,output_tokens=20))
    timing=LongFormTimingManifest(package_sha256=identity,audio_sha256='a'*64,artifact_sha256='b'*64,
        timing_method='measured_scene_audio',duration_seconds=900,
        sections=[dict(section_id=s.section_id,start_seconds=i*15,end_seconds=(i+1)*15) for i,s in enumerate(package.script_sections)])
    return plan,dict(intake=ReferenceIntakeRequest(reference_url=URL,target_duration_seconds=900),
        package_bytes=package_bytes,source_packet_bytes=packet,reference_snapshot_bytes=snapshot_bytes,
        accepted_script_identity=identity,ledger=ledger,timing=timing,audio_sha256='a'*64,artifact_sha256='b'*64)


def test_combined_core_preflight_and_local_evidence_roundtrip(tmp_path):
    plan,args=smoke_inputs()
    report=audit_reference_package(plan,**args)
    assert report['scope']=='local-contract-audit-v1'
    assert report['chapters'].splitlines()==['00:00 Chapter 1','02:30 Chapter 2','05:00 Chapter 3','07:30 Chapter 4','10:00 Chapter 5','12:30 Chapter 6']
    assert report['source_context_bytes']<24000
    assert report['runner_request_bytes']<65536
    assert report['usage']['reserved_calls']==4
    assert report['usage']['narration_attempts']==1
    assert report['usage']['input_tokens']['total']==400
    assert report['usage']['reported_cost_usd']['total'] is None
    assert report['usage']['subscription_fraction'] is None
    output=tmp_path/'local-preflight.json';output.write_text(json.dumps(report,default=str))
    assert json.loads(output.read_text())['package_sha256']==args['accepted_script_identity']
    assert 'approved' not in report and 'published' not in report


@pytest.mark.parametrize('change',['no_approval','stale_source','stale_reference','wrong_budget','pending','no_narration','context_limit','stale_audio','wrong_intake'])
def test_combined_preflight_blocks_conflicting_checkpoints(change):
    plan,args=smoke_inputs()
    if change=='no_approval': args['accepted_script_identity']=None
    elif change=='stale_source': args['source_packet_bytes']+=b' '
    elif change=='stale_reference': args['reference_snapshot_bytes']+=b' '
    elif change=='wrong_budget': args['ledger']=args['ledger'].model_copy(update={'brief_sha256':'0'*64})
    elif change=='pending': args['ledger']=reserve_stage_call(args['ledger'],'repair',brief_sha256=args['ledger'].brief_sha256)
    elif change=='no_narration': args['ledger']=LongFormCallLedger(brief_sha256=args['ledger'].brief_sha256)
    elif change=='context_limit': args['maximum_context_bytes']=100
    elif change=='stale_audio': args['audio_sha256']='0'*64
    else: args['intake']=args['intake'].model_copy(update={'target_duration_seconds':600})
    with pytest.raises(ValueError): audit_reference_package(plan,**args)


def test_provider_or_capture_metadata_does_not_reset_allowance_identity():
    plan,args=smoke_inputs();snapshot=ReferenceSnapshot.model_validate_json(args['reference_snapshot_bytes'])
    key=long_form_brief_identity(plan,reference=snapshot)
    changed=plan.model_copy(update={'request':plan.request.model_copy(update={'script_owner':'claude','script_model':'opus','show_source_credit':True})})
    assert long_form_brief_identity(changed,reference=snapshot)==key
    changed=plan.model_copy(update={'request':plan.request.model_copy(update={'angle':'A revised brief'})})
    assert long_form_brief_identity(changed,reference=snapshot)!=key
