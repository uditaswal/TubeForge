from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from tubeforge.api.app import create_app
from tubeforge.core.config import AppConfig, AuthConfig, DatabaseConfig, Settings
from tubeforge.core.errors import InsufficientSourcesError
from tubeforge.db.models import Base
from tubeforge.domain.contracts import ContentPackage, ScriptSection
from tubeforge.domain.states import JobState
from tubeforge.pipeline.narration import segment_content_package
from tubeforge.providers.content.output import unwrap_generation
from tubeforge.providers.content.prompts import (
    SUPPORTED_CONTENT_TEMPLATE_VERSIONS, build_content_prompt,
    build_repair_prompt, build_revision_prompt, prompt_evidence,
)
from tubeforge.providers.fake import FakeContentProvider
from test_youtube_skills import package, request


@pytest.mark.parametrize('version', sorted(SUPPORTED_CONTENT_TEMPLATE_VERSIONS))
def test_every_generation_and_repair_explicitly_loads_skill_and_complete_brief(version):
    value = request()
    prompts = [build_content_prompt(value, template_version=version, max_chars=60000),
               build_repair_prompt(value, field_path='claims.0.text', invalid_value='x', validation_error='x', template_version=version, max_chars=60000)]
    for prompt in prompts:
        assert 'RESOURCE yt-script/SKILL.md' in prompt
        assert 'RESOURCE yt-script/automation.md' in prompt
        assert 'RESOURCE yt-script/hooks.json' in prompt
        brief = json.loads(prompt.split('BRIEF=', 1)[1].split('\n', 1)[0])
        assert brief['topic'] == value.topic and brief['audience'] == value.audience
        assert brief['language'] == value.language and brief['duration_seconds'] == 45
        assert brief['format']['aspect_ratio'] == '9:16'
        assert brief['tone'] == value.channel_voice_profile
        assert 'approved' in brief['source_requirements']
        assert prompt_evidence(prompt)['automation_mode'] is True
        limits=json.loads(prompt.split('DOMAIN_FIELD_LIMITS=',1)[1].split('\n',1)[0])
        assert limits['ScenePlan.fallback_visual']['maxLength']==100


@pytest.mark.parametrize('raw', [None, 'first few lines', {'status':'ready','package':None,'reason':None},
    {'status':'insufficient_sources','package':package().model_dump(mode='json'),'reason':'missing'},
    {'status':'insufficient_sources','package':None,'reason':''}, package().model_dump(mode='json')])
def test_malformed_generation_never_becomes_a_package(raw):
    with pytest.raises(ValidationError):
        unwrap_generation(raw)


def test_source_failure_has_no_narration_result():
    with pytest.raises(InsufficientSourcesError, match='insufficient_sources: Missing comparison criteria'):
        unwrap_generation({'status':'insufficient_sources','package':None,'reason':'Missing comparison criteria'})


@pytest.mark.parametrize('text', ['[ON SCREEN: git status] Check your changes.', 'Hook 1: You need this.', 'Sources: Git manual', '```json\n{}\n```', '   '])
def test_production_panels_cannot_enter_narration(text):
    with pytest.raises(ValidationError, match='audience-facing speech'):
        ScriptSection(section_id='s1',scene_id='s1',narration=text)


def test_tts_segmentation_reads_only_ordered_narration():
    value = package()
    phrases = segment_content_package(value)
    assert [p.section_id for p in phrases] == sorted([p.section_id for p in phrases])
    assert ' '.join(p.text for p in phrases) == ' '.join(s.narration for s in value.script_sections)
    assert value.hook_options[1] not in ' '.join(p.text for p in phrases)
    assert 'READ FIRST' not in ' '.join(p.text for p in phrases)
    assert 'RESOURCE yt-script/SKILL.md' in build_revision_prompt(value, 'Clarify the steps')


def test_signed_in_source_block_and_revision_prompt_are_truthful(tmp_path):
    settings = Settings(app=AppConfig(name='test',environment='test'), database=DatabaseConfig(url=f'sqlite:///{tmp_path}/studio.db'), auth=AuthConfig(enabled=True,secure_cookies=False))
    settings.pipeline.voice.artifact_root = tmp_path/'artifacts'
    app = create_app(settings); runtime=app.state.runtime
    Base.metadata.create_all(runtime.database.engine)
    runtime.auth.create_admin('operator','long-test-password')
    with TestClient(app) as client:
        assert client.post('/api/jobs/absent/script-revision-prompt',json={'instruction':'Clarify'}).status_code == 401
        assert client.post('/login',json={'username':'operator','password':'long-test-password'}).status_code == 200
        client.headers['x-csrf-token']=client.cookies['tubeforge_csrf']
        blocked = runtime.jobs.create('blocked-job',request())
        runtime.orchestrator.content = FakeContentProvider(failure=InsufficientSourcesError('Missing evidence'))
        result = runtime.orchestrator.run(blocked.id)
        assert result.state == JobState.FAILED_VALIDATION
        assert runtime.artifacts.get(blocked.id,JobState.CONTENT_GENERATING,'content_package') is None
        assert runtime.artifacts.get(blocked.id,JobState.VOICE_GENERATION,'narration') is None
        assert client.get(f'/api/jobs/{blocked.id}').json()['blocked_reason'] == 'insufficient_sources'
        assert client.post(f'/api/jobs/{blocked.id}/script-revision-prompt',json={'instruction':'Clarify'}).status_code == 409
        editable = runtime.jobs.create('editable-job',request())
        runtime.jobs.update_state(editable.id,JobState.SCRIPT_APPROVAL_REQUIRED)
        artifact = runtime.orchestrator._replace_json(editable.id,JobState.CONTENT_GENERATING,'content_package',package().model_dump(mode='json'))
        response=client.post(f'/api/jobs/{editable.id}/script-revision-prompt',json={'instruction':'Clarify'})
        assert response.status_code == 200, response.text
        data=response.json()
        assert data['reviewed_identity'] == artifact.checksum_sha256
        assert 'RESOURCE yt-script/SKILL.md' in data['prompt'] and 'Review the exact script before rendering.' in data['prompt']
        assert data['evidence']['resource_hashes']['yt-script/automation.md']
        assert 'Preparing revision prompt' in client.get('/').text


def test_direct_provider_stops_after_two_failed_invocations(tmp_path):
    from tubeforge.core.config import CodexProviderConfig
    from tubeforge.core.errors import ProviderValidationError, RetryableProviderError
    from tubeforge.db.repositories import GenerationCacheRepository
    from tubeforge.db.session import create_database
    from tubeforge.providers.content.codex_cli import CodexCliContentProvider, ProcessResult
    database=create_database(DatabaseConfig(url=f'sqlite:///{tmp_path}/cache.db'))
    Base.metadata.create_all(database.engine)
    calls=[]
    def timeout(*args):
        calls.append(args[1]); return ProcessResult(124,b'',b'timeout')
    provider=CodexCliContentProvider(CodexProviderConfig(prompt_template_version='m6-content-v6'),GenerationCacheRepository(database.session_factory),process_runner=timeout)
    for _ in range(2):
        with pytest.raises(RetryableProviderError): provider.generate_package(request())
    with pytest.raises(ProviderValidationError,match='two-attempt limit'): provider.generate_package(request())
    assert len(calls)==2
    assert all('RESOURCE yt-script/SKILL.md' in prompt for prompt in calls)
    database.dispose()


def test_direct_provider_refusal_is_not_cached_as_content(tmp_path):
    from tubeforge.core.config import CodexProviderConfig
    from tubeforge.db.repositories import GenerationCacheRepository
    from tubeforge.db.session import create_database
    from tubeforge.providers.content.codex_cli import CodexCliContentProvider, ProcessResult
    database=create_database(DatabaseConfig(url=f'sqlite:///{tmp_path}/cache.db'))
    Base.metadata.create_all(database.engine)
    def refused(_args,prompt,output,*_):
        output.write_text(json.dumps({'status':'insufficient_sources','package':None,'reason':'Missing topic support'}))
        return ProcessResult(0,b'',b'')
    provider=CodexCliContentProvider(CodexProviderConfig(prompt_template_version='m6-content-v6'),GenerationCacheRepository(database.session_factory),process_runner=refused)
    with pytest.raises(InsufficientSourcesError,match='Missing topic support'): provider.generate_package(request())
    assert provider.last_provenance is None
    database.dispose()


def test_saved_revision_requires_fresh_exact_approval(tmp_path):
    from test_codex_content import package as legacy_package, request as legacy_request
    value=legacy_request(prompt_version='m6-content-v6')
    settings=Settings(app=AppConfig(name='test',environment='test'), database=DatabaseConfig(url=f'sqlite:///{tmp_path}/revisions.db'))
    settings.pipeline.voice.artifact_root=tmp_path/'artifacts'
    app=create_app(settings);runtime=app.state.runtime;Base.metadata.create_all(runtime.database.engine)
    job=runtime.jobs.create('exact-revision',value)
    runtime.jobs.update_state(job.id,JobState.SCRIPT_APPROVAL_REQUIRED)
    original=runtime.orchestrator._replace_json(job.id,JobState.CONTENT_GENERATING,'content_package',legacy_package(value))
    with TestClient(app) as client:
        approve={'status':'approved','actor':'test','reviewed_identity':original.checksum_sha256}
        assert client.post(f'/api/jobs/{job.id}/approvals/script',json=approve).status_code==200
        narrations=[s['narration'] for s in legacy_package(value)['script_sections']]
        bad=list(narrations);bad[0]='[ON SCREEN: clouds] Sources: manual'
        assert client.post(f'/api/jobs/{job.id}/script-revision',json={'narrations':bad}).status_code==422
        narrations[-1]='Check your weather notes before recording the next explanation.'
        response=client.post(f'/api/jobs/{job.id}/script-revision',json={'narrations':narrations})
        assert response.status_code==200,response.text
        revised_identity=response.json()['reviewed_identity'];assert revised_identity!=original.checksum_sha256
        assert runtime.orchestrator.run(job.id).state==JobState.SCRIPT_APPROVAL_REQUIRED
        assert runtime.artifacts.get(job.id,JobState.VOICE_GENERATION,'narration') is None
        approve['reviewed_identity']=revised_identity
        assert client.post(f'/api/jobs/{job.id}/approvals/script',json=approve).status_code==200
        runtime.orchestrator._run_stage(runtime.jobs.get(job.id))
        assert runtime.jobs.get(job.id).state==JobState.ASSET_ACQUISITION
        saved=ContentPackage.model_validate(runtime.orchestrator._required_json(job.id,JobState.CONTENT_GENERATING,'content_package'))
        assert segment_content_package(saved)[-1].text==narrations[-1]


def test_signed_in_scene_edit_creates_separate_review_draft(tmp_path):
    settings=Settings(app=AppConfig(name='test',environment='test'),database=DatabaseConfig(url=f'sqlite:///{tmp_path}/scene-edit.db'),auth=AuthConfig(enabled=True,secure_cookies=False))
    settings.pipeline.voice.artifact_root=tmp_path/'artifacts'
    app=create_app(settings);runtime=app.state.runtime;Base.metadata.create_all(runtime.database.engine)
    runtime.auth.create_admin('operator','long-test-password')
    value=request().model_copy(update={'aspect_ratio':'16:9'})
    parent=runtime.jobs.create('scene-parent',value)
    runtime.jobs.update_state(parent.id,JobState.SCRIPT_APPROVAL_REQUIRED)
    original=runtime.orchestrator._replace_json(parent.id,JobState.CONTENT_GENERATING,'content_package',package().model_copy(update={'request':value}).model_dump(mode='json'))
    scene=package().scene_plans[0]
    body={'scene_id':scene.scene_id,'expected_content_sha256':original.checksum_sha256,'visual_subject':'A more explicit source-grounded diagram','actor':'operator'}
    with TestClient(app) as client:
        assert client.post(f'/api/jobs/{parent.id}/scene-revisions',json=body).status_code==401
        assert client.post('/login',json={'username':'operator','password':'long-test-password'}).status_code==200
        client.headers['x-csrf-token']=client.cookies['tubeforge_csrf']
        stale={**body,'expected_content_sha256':'0'*64}
        assert client.post(f'/api/jobs/{parent.id}/scene-revisions',json=stale).status_code==409
        assert client.post(f'/api/jobs/{parent.id}/scene-revisions',json={**body,'visual_subject':scene.visual_subject}).status_code==422
        response=client.post(f'/api/jobs/{parent.id}/scene-revisions',json=body)
        assert response.status_code==201,response.text
        child=response.json()['job_id']
        assert child!=parent.id and response.json()['state']=='script_approval_required'
        assert runtime.jobs.get(child).state==JobState.SCRIPT_APPROVAL_REQUIRED
        assert runtime.artifacts.get(parent.id,JobState.CONTENT_GENERATING,'content_package').checksum_sha256==original.checksum_sha256
        assert response.json()['reviewed_identity']!=original.checksum_sha256
        stale_approval={'status':'approved','actor':'operator','reviewed_identity':original.checksum_sha256}
        assert client.post(f'/api/jobs/{child}/approvals/script',json=stale_approval).status_code==409
        assert client.get(f'/api/jobs/{child}/events').json()[-1]['event_type']=='scene_revision_created'
        assert client.get(f'/api/jobs/{child}/script').json()['package']['scene_plans'][0]['visual_subject']==body['visual_subject']
        assert any(event['event_type']=='scene_revision_created' and event['details']['child_job_id']==child for event in client.get(f'/api/jobs/{parent.id}/events').json())
        assert any(event['event_type']=='scene_revision_created' and event['details']['parent_job_id']==parent.id for event in client.get(f'/api/jobs/{child}/events').json())
        assert client.get('/').status_code==200
        assert 'id="sceneDialog"' in client.get('/').text
        assert 'Revise one scene' in client.get('/').text


def test_host_source_failure_blocks_before_script_or_tts(tmp_path):
    from tubeforge.core.config import CodexProviderConfig
    from tubeforge.db.repositories import GenerationCacheRepository
    from tubeforge.providers.content.host_runner import HostRunnerContentProvider
    from tubeforge.providers.content.host_runner_protocol import HostRunnerResponse, HostRunnerSuccess
    from tubeforge.providers.content.youtube_skills import preflight
    settings=Settings(app=AppConfig(name='test',environment='test'),database=DatabaseConfig(url=f'sqlite:///{tmp_path}/host-failure.db'))
    settings.pipeline.voice.artifact_root=tmp_path/'artifacts'
    app=create_app(settings);runtime=app.state.runtime;Base.metadata.create_all(runtime.database.engine)
    operations=[]
    def transport(_path,payload,_timeout):
        operation=json.loads(payload)['operation'];operations.append(operation)
        if operation=='PreflightContentV1':
            return HostRunnerResponse(ok=True,result=HostRunnerSuccess(package={},provenance={'resource_hashes':preflight(),'prompt_sha256':prompt_evidence(build_content_prompt(request(),template_version=request().prompt_version,max_chars=60000))['prompt_sha256']})).model_dump_json().encode()
        return HostRunnerResponse(ok=False,failure={'code':'insufficient_sources','message':'No supported comparison criteria','invocation_started':True}).model_dump_json().encode()
    runtime.orchestrator.content=HostRunnerContentProvider(CodexProviderConfig(),GenerationCacheRepository(runtime.database.session_factory),transport=transport)
    job=runtime.jobs.create('host-source-block',request())
    result=runtime.orchestrator.run(job.id)
    assert result.state==JobState.FAILED_VALIDATION
    assert operations==['PreflightContentV1','GenerateShortsScriptV1']
    assert runtime.artifacts.get(job.id,JobState.CONTENT_GENERATING,'content_package') is None
    assert runtime.artifacts.get(job.id,JobState.VOICE_GENERATION,'narration') is None
    with TestClient(app) as client:
        assert client.get(f'/api/jobs/{job.id}').json()['blocked_reason']=='insufficient_sources'


def test_cli_envelope_exposes_existing_candidate_count_gates():
    from tubeforge.host_codex_runner import codex_output_schema
    schema=codex_output_schema(envelope=True)
    assert schema['$defs']['VideoMetadata']['properties']['title_options']['minItems']==10
    assert schema['$defs']['ContentPackage']['properties']['hook_options']['minItems']==5


def test_host_rejected_packaging_returns_draft_without_acceptance(monkeypatch,tmp_path):
    import subprocess
    from tubeforge import host_codex_runner as runner
    from tubeforge.providers.content.host_runner_protocol import GenerateShortsScriptRequest
    draft=package().model_dump(mode='json');draft['metadata']['title_options']=['Only one title']
    monkeypatch.setattr(runner,'bubblewrap_args',lambda _workspace:['fixed-codex-command'])
    def model_output(command,**kwargs):
        output=next((tmp_path/'outputs').glob('*/content-package.schema.json')).with_name('content-package.json')
        output.write_text(json.dumps({'status':'ready','package':draft,'reason':None}))
        return subprocess.CompletedProcess(command,0,b'',b'')
    monkeypatch.setattr(runner.subprocess,'run',model_output)
    with pytest.raises(runner.RejectedContentError,match='ten title_options') as rejected:
        runner.run_request(GenerateShortsScriptRequest(request=package().request),root=tmp_path)
    assert rejected.value.result.package==draft
    assert rejected.value.result.provenance['invocations'][0]['skill_loaded']=='yt-script/SKILL.md'
    assert not list((tmp_path/'outputs').glob('*/content-package.json'))
