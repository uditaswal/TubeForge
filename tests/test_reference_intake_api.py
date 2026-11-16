import hashlib
import json

import pytest
from fastapi.testclient import TestClient
from alembic import command
from sqlalchemy import text

from tubeforge.api.app import create_app
from tubeforge.core.config import Settings,AppConfig,DatabaseConfig,AuthConfig
from test_api_workflow import _migrate
from test_reference_intake_extractor import URL,FixtureHTTP,player
from tubeforge.reference.extractor import YoutubeReferenceExtractor


@pytest.fixture
def api(tmp_path):
    path=tmp_path/'api.db';_migrate(path)
    app=create_app(Settings(app=AppConfig(name='TubeForge reference test',environment='test'),database=DatabaseConfig(url=f'sqlite:///{path}'),auth=AuthConfig(enabled=True)))
    app.state.runtime.auth.create_admin('reference-reviewer','test-only-intake-password')
    app.state.runtime.reference_intakes.extractor=YoutubeReferenceExtractor(FixtureHTTP())
    with TestClient(app) as client:
        assert client.post('/login',json={'username':'reference-reviewer','password':'test-only-intake-password'}).status_code==200
        headers={'x-csrf-token':client.cookies.get('tubeforge_csrf')}
        yield client,app.state.runtime,headers


def submit(client,headers,**updates):
    return client.post('/api/reference-intakes',json=dict(reference_url=URL,target_duration_seconds=600,**updates),headers=headers)


def test_auth_csrf_create_worker_detail_and_exact_snapshot_export(api):
    client,runtime,headers=api
    assert submit(client,{}).status_code==403
    created=submit(client,headers);assert created.status_code==201
    value=created.json()['intake'];assert value['state']=='pending'
    assert runtime.reference_intakes.extractor.http.calls==[]
    assert '/references' in client.get('/').text
    assert 'Reference videos' in client.get('/references').text
    runtime.reference_intakes.run_once('test-worker')
    ready=client.get('/api/reference-intakes/'+value['intake_id']).json()['intake'];assert ready['state']=='ready'
    exported=client.get('/api/reference-intakes/'+value['intake_id']+'/snapshot')
    assert exported.status_code==200
    assert hashlib.sha256(exported.content).hexdigest()==ready['reference_snapshot_sha256']
    duplicate=submit(client,headers).json()['intake'];assert duplicate['intake_id']==value['intake_id']
    assert runtime.reference_intakes.run_once('test-worker') is None
    assert len(runtime.reference_intakes.extractor.http.calls)==2
    assert client.get('/api/jobs').json()==[]
    client.cookies.clear()
    assert client.get('/api/reference-intakes').status_code==401
    assert client.get('/references',follow_redirects=False).status_code==303


def test_missing_captions_supplied_srt_revision_and_preserved_history(api):
    client,runtime,headers=api;raw=player();raw['captions']={}
    runtime.reference_intakes.extractor=YoutubeReferenceExtractor(FixtureHTTP(raw))
    original=submit(client,headers).json()['intake'];key=original['intake_id']
    runtime.reference_intakes.run_once('worker')
    assert client.get('/api/reference-intakes/'+key).json()['intake']['state']=='needs_input'
    srt='1\n00:00:00,000 --> 00:00:04,000\nSupplied fixture caption.\n'
    revised=client.post(f'/api/reference-intakes/{key}/revisions',json=dict(expected_revision=1,action='transcript',transcript_text=srt),headers=headers)
    assert revised.status_code==201 and revised.json()['intake']['revision']==2
    stale=client.post(f'/api/reference-intakes/{key}/revisions',json=dict(expected_revision=1,action='refresh'),headers=headers)
    assert stale.status_code==409
    runtime.reference_intakes.run_once('worker')
    ready=client.get('/api/reference-intakes/'+key).json()
    assert ready['intake']['state']=='ready' and ready['intake']['snapshot']['transcript_origin']=='supplied'
    assert len(runtime.reference_intakes.extractor.http.calls)==1
    assert client.get(f'/api/reference-intakes/{key}?revision=1').json()['intake']['state']=='needs_input'
    assert any(e['actor']=='reference-reviewer' for e in ready['activity'])


@pytest.mark.parametrize('update',[{'reference_url':'https://127.0.0.1/private'}, {'target_duration_seconds':599}, {'channel_identity':'unknown'}, {'reference_snapshot_sha256':'a'*64}, {'approved':True}])
def test_invalid_or_forged_inputs_are_rejected_without_work(api,update):
    client,runtime,headers=api
    raw=dict(reference_url=URL,target_duration_seconds=600);raw.update(update)
    assert client.post('/api/reference-intakes',json=raw,headers=headers).status_code==422
    assert runtime.reference_intakes.extractor.http.calls==[]
    assert client.get('/api/reference-intakes').json()['items']==[]


def test_pending_cancel_and_invalid_transcript_have_truthful_durable_states(api):
    client,runtime,headers=api;value=submit(client,headers).json()['intake'];path=f'/api/reference-intakes/{value["intake_id"]}/revisions'
    assert client.get(f'/api/reference-intakes/{value["intake_id"]}/snapshot').status_code==409
    cancelled=client.post(path,json=dict(expected_revision=1,action='cancel'),headers=headers)
    assert cancelled.status_code==201 and cancelled.json()['intake']['failure_code']=='cancelled'
    assert runtime.reference_intakes.run_once('worker') is None
    assert client.post(path,json=dict(expected_revision=1,action='transcript',transcript_text='no timestamps'),headers=headers).status_code==422
    assert client.post(path,json=dict(expected_revision=1,action='refresh'),headers=headers).status_code==201


def test_oversized_request_never_enqueues(api):
    client,runtime,headers=api
    assert client.post('/api/reference-intakes',content=b' '*2000001,headers=headers).status_code==413
    assert client.get('/api/reference-intakes').json()['items']==[]


@pytest.mark.parametrize('target', [25, 30, 60, 90, 600, 720, 900])
def test_reference_intake_accepts_short_and_long_form_targets(api, target):
    client, runtime, headers = api
    response = client.post('/api/reference-intakes', json=dict(reference_url=URL, target_duration_seconds=target), headers=headers)
    assert response.status_code == 201
    assert response.json()['intake']['request']['target_duration_seconds'] == target
    assert client.get('/api/jobs').json() == []


@pytest.mark.parametrize('target', [24, 121, 599, 901])
def test_reference_intake_rejects_unsupported_duration_gap(api, target):
    client, runtime, headers = api
    assert client.post('/api/reference-intakes', json=dict(reference_url=URL, target_duration_seconds=target), headers=headers).status_code == 422
    assert runtime.reference_intakes.extractor.http.calls == []
