"""Durable routing choices through the signed-in API, with no worker or live calls."""
import pytest
from fastapi.testclient import TestClient
from tubeforge.api.app import create_app
from tubeforge.core.config import AppConfig, AuthConfig, DatabaseConfig, Settings, VideoPresetConfig
from tubeforge.db.models import Base
from tubeforge.db.session import create_database
from tubeforge.domain.contracts import ContentRequest, generation_request_key_payload
from test_script_owner import request


def test_routing_metadata_is_omitted_from_legacy_requests_and_writer_identity():
    legacy=request()
    automatic=request(script_routing_mode='automatic')
    assert 'script_routing_mode' not in legacy.model_dump(mode='json')
    assert generation_request_key_payload(legacy)==generation_request_key_payload(automatic)
    assert ContentRequest.model_validate_json(automatic.model_dump_json()).script_routing_mode=='automatic'
    with pytest.raises(ValueError):
        request(script_routing_mode='anything')


def settings_for(tmp_path, enabled=True):
    settings=Settings(app=AppConfig(name='routing test',environment='test'),database=DatabaseConfig(url=f'sqlite:///{tmp_path / "routing.db"}'),auth=AuthConfig(enabled=True),pipeline={'claude':{'enabled':enabled}})
    settings.pipeline.video_generation.presets['shorts']=VideoPresetConfig(duration_seconds=60,minimum_duration_seconds=30,maximum_duration_seconds=90,aspect_ratio='9:16',prompt_version='m6-content-v8')
    database=create_database(settings.database)
    Base.metadata.create_all(database.engine)
    database.dispose()
    return settings


def sign_in(client, create=False):
    if create:client.app.state.runtime.auth.create_admin('operator','correct-horse-battery-staple')
    assert client.post('/login',json={'username':'operator','password':'correct-horse-battery-staple'}).status_code==200
    client.headers['x-csrf-token']=client.cookies['tubeforge_csrf']


def test_three_modes_persist_across_app_restart_and_review(tmp_path):
    settings=settings_for(tmp_path)
    ids={}
    with TestClient(create_app(settings)) as client:
        assert client.post('/api/videos',json={'title':'Test','notes':['Example'],'script_routing_mode':'automatic'}).status_code==401
        sign_in(client,True)
        client.headers.pop('x-csrf-token')
        assert client.post('/api/videos',json={'title':'Test','notes':['Example'],'script_routing_mode':'automatic'}).status_code==403
        client.headers['x-csrf-token']=client.cookies['tubeforge_csrf']
        for mode,owner in [('claude_only','claude'),('codex_only','codex'),('automatic','claude')]:
            response=client.post('/api/videos',json={'title':'Test','notes':['An example'],'script_routing_mode':mode})
            assert response.status_code==201,response.text
            job=client.app.state.runtime.jobs.get(response.json()['id'])
            assert job.request.script_owner==owner
            assert job.request.script_routing_mode==mode
            ids[mode]=job.id
    with TestClient(create_app(settings)) as client:
        sign_in(client)
        jobs=client.get('/api/jobs').json()
        for mode,id in ids.items():
            job=client.app.state.runtime.jobs.get(id)
            assert job.request.script_routing_mode==mode
            assert next(row for row in jobs if row['id']==id)['script_routing_mode']==mode


def test_disabled_claude_rejects_automatic_and_claude_only_but_allows_codex(tmp_path):
    with TestClient(create_app(settings_for(tmp_path,False))) as client:
        sign_in(client,True)
        for mode in ['automatic','claude_only']:
            response=client.post('/api/videos',json={'title':'Test','notes':['Example'],'script_routing_mode':mode})
            assert response.status_code==422
        assert client.post('/api/videos',json={'title':'Test','notes':['Example'],'script_routing_mode':'codex_only'}).status_code==201


def test_saved_policy_is_audited_inherited_and_does_not_retarget_old_jobs(tmp_path):
    from sqlalchemy import select
    from tubeforge.db.models import ScriptRoutingPolicyRecord
    settings=settings_for(tmp_path)
    with TestClient(create_app(settings)) as client:
        assert client.put('/api/script-routing',json={'mode':'codex_only','preferred_model':'gpt-sol','expected_revision':0}).status_code==401
        sign_in(client,True)
        initial=client.get('/api/script-routing').json()
        assert initial['mode'] is None
        client.headers.pop('x-csrf-token')
        assert client.put('/api/script-routing',json={'mode':'codex_only','preferred_model':'gpt-sol','expected_revision':0}).status_code==403
        client.headers['x-csrf-token']=client.cookies['tubeforge_csrf']
        saved=client.put('/api/script-routing',json={'mode':'codex_only','preferred_model':'gpt-sol','expected_revision':0})
        assert saved.status_code==200,saved.text
        first=client.post('/api/videos',json={'title':'First','notes':['Example']}).json()['id']
        runtime=client.app.state.runtime
        assert runtime.jobs.get(first).request.script_routing_mode=='codex_only'
        assert runtime.jobs.get(first).request.script_owner=='codex'
        assert runtime.scheduler.request_transform(request()).script_routing_mode=='codex_only'
        from tubeforge.batch_plans import BatchShort
        batch=runtime.scheduler.batch_request_factory(BatchShort(id='one',title='One',concept='Example',beats=[{'t':0,'point':'Example'}]))
        assert batch.script_owner=='codex' and batch.script_routing_mode=='codex_only'
        stale=client.put('/api/script-routing',json={'mode':'claude_only','preferred_model':'opus','expected_revision':0})
        assert stale.status_code==409
        saved=client.put('/api/script-routing',json={'mode':'claude_only','preferred_model':'opus','expected_revision':saved.json()['revision']})
        assert saved.status_code==200
        second=client.post('/api/videos',json={'title':'Second','notes':['Example']}).json()['id']
        assert runtime.jobs.get(second).request.script_owner=='claude'
        assert runtime.jobs.get(second).request.script_model=='opus'
        assert runtime.jobs.get(first).request.script_owner=='codex'
        with runtime.database.session_factory() as session:
            history=list(session.scalars(select(ScriptRoutingPolicyRecord)))
            assert len(history)==2 and all(row.actor and row.created_at for row in history)
    with TestClient(create_app(settings)) as client:
        sign_in(client)
        assert client.get('/api/script-routing').json()['mode']=='claude_only'
        assert client.app.state.runtime.jobs.get(first).request.script_routing_mode=='codex_only'
