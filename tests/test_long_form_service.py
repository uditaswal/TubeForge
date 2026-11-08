"""Complete LF2 preparation through typed socket envelopes and durable mock hosts."""
from datetime import UTC,datetime,timedelta
import json
from types import SimpleNamespace

import pytest
from tubeforge.core.config import Settings,AppConfig,DatabaseConfig
from tubeforge.db.models import Base
from tubeforge.db.session import create_database
from tubeforge.db.long_form_writing import LongFormWritingRepository,json_text,sha
from tubeforge.domain.contracts import ContentRequest
from tubeforge.domain.long_form_writing import LongFormDraftResult,LongFormHostRequest
from tubeforge.long_form.client import LongFormHostClient
from tubeforge.long_form.host import handle
from tubeforge.long_form.service import LongFormWritingService
from tubeforge.long_form.admission import measure
from tubeforge.providers.content.host_runner_protocol import HostRunnerResponse
from test_long_form_writing import writing_inputs,review_result


@pytest.fixture
def workflow(tmp_path):
    database=create_database(DatabaseConfig(url=f'sqlite:///{tmp_path}/writing.db'));Base.metadata.create_all(database.engine)
    now=[datetime(2026,11,8,tzinfo=UTC)];repo=LongFormWritingRepository(database.session_factory,clock=lambda:now[0])
    template,draft,reference,packet=writing_inputs()
    intake={'intake':{'state':'ready','snapshot':reference.model_dump(mode='json'),'request':{'channel_identity':'default','language':'en','target_duration_seconds':600}}}
    intakes=SimpleNamespace(get=lambda *args:intake)
    settings=Settings(app=AppConfig(name='LF2 isolated workflow',environment='test'),database=DatabaseConfig(url=f'sqlite:///{tmp_path}/writing.db'))
    settings.pipeline.codex.model='fixture-model'
    state=dict(mode='pass',lost=False,launches=[],captures=0,cancel_on_launch=False,stop_on_prepare=False,stopped=False,run_id=None)
    def invoke(message):
        state['launches'].append(message.stage)
        if state['cancel_on_launch']:repo.cancel(state['run_id'],'operator')
        if message.stage=='research':
            output={'status':'ready','assessment':'Synthetic research only.','sources':[{'source_id':s.source_id,'url':str(s.url),'title':s.title} for s in template.request.sources]}
        elif message.stage=='review':
            output=review_result().model_dump(mode='json')
            if state['mode']=='review_repair':output=review_result(decision='repair',findings=[dict(severity='blocker',category='clarity',section_ids=['section-1'],detail='Synthetic fixture needs a clearer example.')]).model_dump(mode='json')
        else:
            raw=draft.model_dump(mode='json');raw['package']['request']=message.request.model_dump(mode='json')
            if message.stage=='repair':raw['package']['script_sections'][1]['narration']=raw['package']['script_sections'][1]['narration'].replace('Synthetic','Separate',1)
            if state['mode']=='both_bad' or (state['mode']=='first_bad' and message.stage=='draft'):
                output=None
            else:output=raw;output['package'].pop('request')
        evidence=dict(output=output,raw_output='{bad synthetic output' if output is None else None,
            usage={'input_tokens':1000,'output_tokens':500},provenance={'model':'fixture-model','prompt_sha256':measure(message)['prompt_sha256'],'web_searches':1 if message.stage=='research' else 0})
        if state['mode']=='unknown_usage':evidence['usage']=None
        return evidence
    def transport(path,payload,timeout):
        message=LongFormHostRequest.model_validate_json(payload)
        result=handle(message,provider='codex',root=tmp_path/'host',invoke=invoke,check_runtime=lambda:None,model='fixture-model')
        if message.operation=='PrepareLongFormCallV1' and state['stop_on_prepare']:state['stopped']=True
        if message.operation=='LongFormStageV1' and state['mode']=='lost_response' and not state['lost']:
            state['lost']=True;raise ConnectionResetError('simulated lost reply after completed invocation')
        return HostRunnerResponse(ok=True,result=result).model_dump_json().encode()
    client=LongFormHostClient(settings.pipeline.codex,settings.pipeline.claude,transport=transport)
    def capture(request,research,**kwargs):
        state['captures']+=1
        canonical=ContentRequest.model_validate({**request.model_dump(mode='json'),'sources':[s.model_dump(mode='json') for s in template.request.sources]})
        return canonical,{'schema_version':'1.1','sources':[s.model_dump(mode='json') for s in canonical.sources],'research_assessment':research.assessment}
    service=LongFormWritingService(repo,intakes,client,settings,source_capture=capture)
    run=service.create(intake_id='intake',intake_revision=1,topic=template.request.topic,angle=template.request.angle,audience=template.request.audience)
    state['run_id']=run['id']
    yield service,repo,now,state,client
    database.dispose()


def tick(service,repo,state):
    result=service.run_once('test-worker')
    return repo.get(state['run_id']) if result is None else result


def test_grounded_script_preparation_stops_at_exact_review_without_rendering(workflow):
    service,repo,_,state,_=workflow
    for _ in range(3):run=tick(service,repo,state)
    assert run['state']=='awaiting_review',run['message']
    assert state['launches']==['research','draft','review'] and state['captures']==1
    assert run['usage']['reserved_calls']==3 and run['usage']['narration_attempts']==1
    assert run['score_report']['tools_executed']==['hookscore.py','title.py']
    assert len(run['planning']['chapters'])==3 and run['review_applies_to_current_draft']
    assert run['decisions']==[] and service.run_once('test-worker') is None


def test_lost_response_restart_inspects_saved_result_without_new_invocation(workflow):
    service,repo,now,state,_=workflow;state['mode']='lost_response'
    run=tick(service,repo,state);assert run['state']=='reconciling'
    assert state['launches']==['research']
    now[0]+=timedelta(seconds=6)
    restarted=LongFormWritingService(repo,service.intakes,service.client,service.settings,source_capture=service.source_capture)
    run=tick(restarted,repo,state);assert run['next_stage']=='draft' and state['launches']==['research']
    tick(restarted,repo,state);run=tick(restarted,repo,state)
    assert run['state']=='awaiting_review' and state['launches']==['research','draft','review']


@pytest.mark.parametrize('mode',['first_bad','review_repair'])
def test_one_repair_retains_original_and_reports_review_binding(workflow,mode):
    service,repo,_,state,_=workflow;state['mode']=mode
    for _ in range(4):run=tick(service,repo,state)
    assert run['state']=='awaiting_review',run['message']
    assert run['usage']['narration_attempts']==2 and len(run['calls'])==4
    assert sorted(state['launches'])==sorted(['research','draft','review','repair'])
    if mode=='first_bad':
        assert run['calls'][1]['response']['result']['raw_output']=='{bad synthetic output'
        assert any(e['event']=='draft_rejected' for e in run['activity'])
        assert run['review_applies_to_current_draft']
    else:
        assert not run['review_applies_to_current_draft']
        assert 'earlier draft' in run['message']


def test_two_rejected_narration_attempts_stop_without_another_call(workflow):
    service,repo,_,state,_=workflow;state['mode']='both_bad'
    for _ in range(3):run=tick(service,repo,state)
    assert run['state']=='exhausted' and state['launches']==['research','draft','repair']
    assert len([e for e in run['activity'] if e['event']=='draft_rejected'])==2
    assert service.run_once('test-worker') is None


def test_unknown_usage_blocks_instead_of_reserving_more_model_calls(workflow):
    service,repo,_,state,_=workflow;state['mode']='unknown_usage'
    run=tick(service,repo,state)
    assert run['state']=='blocked' and run['usage']['input_tokens']['total'] is None
    assert state['launches']==['research'] and state['captures']==0
    assert service.run_once('test-worker') is None


def test_cancelled_owner_cannot_promote_a_late_model_result(workflow):
    service,repo,_,state,client=workflow;state['cancel_on_launch']=True
    run=tick(service,repo,state)
    assert run['state']=='cancelled' and run['draft'] is None and state['captures']==0
    saved=repo.stage_call(run['id'],'research')
    assert client.receipt(saved['message'],'InspectLongFormCallV1')['state']=='succeeded'
    assert service.run_once('test-worker') is None


def test_shutdown_after_prepare_does_not_start_a_model_and_restart_reuses_receipt(workflow):
    service,repo,now,state,_=workflow;state['stop_on_prepare']=True
    service.run_once('stopping-worker',cancelled=lambda:state['stopped'])
    assert state['launches']==[]
    call=repo.stage_call(state['run_id'],'research');assert call['state']=='prepared'
    state['stopped']=False;state['stop_on_prepare']=False;now[0]+=timedelta(seconds=1201)
    run=tick(service,repo,state)
    assert run['next_stage']=='draft' and state['launches']==['research']


def test_existing_media_worker_lease_prevents_lf2_dispatch(workflow):
    service,repo,_,state,_=workflow
    assert service.heavy_work.acquire('existing-media-worker',now=repo.clock(),lease_seconds=600)
    assert service.run_once('test-worker') is None and state['launches']==[]
    assert repo.get(state['run_id'])['state']=='pending'
    service.heavy_work.release('existing-media-worker')
    assert tick(service,repo,state)['next_stage']=='draft'
    assert state['launches']==['research']


def test_disconnect_while_host_runs_retains_global_exclusion_until_receipt_finishes(workflow,monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    import threading
    service,repo,now,state,client=workflow
    running=threading.Event();finish=threading.Event()
    original_handle=handle;original_transport=client.transport
    def slow_handle(message,**options):
        original_invoke=options['invoke']
        def blocked_invoke(message):
            running.set()
            assert finish.wait(timeout=10)
            return original_invoke(message)
        return original_handle(message,**{**options,'invoke':blocked_invoke})
    monkeypatch.setattr('test_long_form_service.handle',slow_handle)
    futures=[]
    with ThreadPoolExecutor(max_workers=1) as pool:
        def disconnected(path,payload,timeout):
            message=LongFormHostRequest.model_validate_json(payload)
            if message.operation=='LongFormStageV1' and not futures:
                futures.append(pool.submit(original_transport,path,payload,timeout))
                assert running.wait(timeout=5)
                raise ConnectionResetError('socket dropped while the host is still running')
            return original_transport(path,payload,timeout)
        client.transport=disconnected
        try:
            run=tick(service,repo,state)
            assert run['state']=='reconciling'
            assert not service.heavy_work.acquire('media-worker',now=now[0],lease_seconds=60)
            now[0]+=timedelta(seconds=6)
            run=tick(service,repo,state)
            assert run['state']=='reconciling' and len(futures)==1
            assert not service.heavy_work.acquire('other-provider-worker',now=now[0],lease_seconds=60)
            other=service.create(intake_id='intake',intake_revision=1,topic='Different exact brief',angle='Another angle',audience='Developers')
            assert service.run_once('other-worker') is None
            assert repo.get(other['id'])['state']=='pending'
        finally:finish.set()
        futures[0].result(timeout=5)
    now[0]+=timedelta(seconds=6)
    run=tick(service,repo,state)
    assert run['next_stage']=='draft' and state['launches']==['research']
    assert service.heavy_work.acquire('media-worker',now=now[0],lease_seconds=60)
