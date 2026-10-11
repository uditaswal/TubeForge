from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from tubeforge.api.app import create_app
from tubeforge.core.config import AppConfig, AuthConfig, CodexProviderConfig, DatabaseConfig, Settings, VideoPresetConfig
from tubeforge.core.errors import ProviderValidationError
from tubeforge.db.models import Base, GenerationCacheRecord
from tubeforge.db.repositories import Artifact, GenerationCacheRepository
from tubeforge.db.session import create_database
from tubeforge.domain.contracts import ContentPackage, ContentRequest, SourceReference
from tubeforge.core.state_machine import JobState
from tubeforge.providers.content import youtube_skills as skills
from tubeforge.providers.content.host_runner import HostRunnerContentProvider
from tubeforge.providers.content.host_runner_protocol import HostRunnerResponse, HostRunnerSuccess
from tubeforge.providers.content.prompts import build_content_prompt
from tubeforge.providers.fake import FakeContentProvider
from tubeforge.scheduling.service import request_from_topic


def request():
    return ContentRequest(topic="Review a video", angle="Exact script review", target_duration_seconds=45,
                          aspect_ratio="9:16", language="en", audience="creators", prompt_version=skills.SKILL_TEMPLATE,
                          sources=(SourceReference(source_id="review", url="https://local.invalid/review", title="Review", excerpt="Review the exact script before rendering."),))


def package():
    value = FakeContentProvider().generate_package(request()).model_dump(mode="json")
    hooks = ["Why should you review your exact script before rendering?", "Check your exact script before you render this video.", "Your script needs review before rendering starts.", "What does your script review actually protect?", "How can you check your script before rendering?"]
    value['hook_options'] = hooks
    value['script_sections'][0]['narration'] = hooks[0] + ' Review the exact saved source and narration before rendering your video.'
    value['metadata']['title_options'] = [f"Script review: {i} checks" for i in range(1, 11)]
    value['thumbnail_brief']['text_options'] = ['READ FIRST']
    for scene in value['scene_plans']:
        scene['on_screen_text'] = 'Review exact script'
    return ContentPackage.model_validate(value)


def test_bundled_instructions_and_tools_are_bounded_and_real():
    prompt = build_content_prompt(request(), template_version=skills.SKILL_TEMPLATE, max_chars=60000)
    for name in skills.RESOURCES:
        assert f'RESOURCE {name}/SKILL.md' in prompt
    assert 'hooks.json' in prompt and 'hookscore.py' in prompt and 'title.py' in prompt
    assert '~/.claude' not in prompt and 'channel_voice_profile' in prompt
    report = skills.evaluate(package())
    assert report['tools_executed'] == ['hookscore.py', 'title.py']
    assert len(report['hooks']) == 5 and len(report['titles']) == 10
    assert sum(row['selected'] for row in report['hooks']) == 1
    assert report['hooks'][0]['verdict'] >= report['hooks'][-1]['verdict']
    assert len(report['resource_hashes']) == 7


def test_missing_resource_and_invalid_candidate_fail_explicitly(tmp_path):
    with pytest.raises(ProviderValidationError, match='preflight failed'):
        skills.preflight(tmp_path)
    malformed = package().model_copy(update={'hook_options': ('wrong',)})
    with pytest.raises(ProviderValidationError, match='five distinct'):
        skills.evaluate(malformed)


def test_remote_preflight_failure_does_not_reserve_or_count(tmp_path):
    database = create_database(DatabaseConfig(url=f'sqlite:///{tmp_path}/cache.db'))
    Base.metadata.create_all(database.engine)
    calls = []
    def transport(_path, payload, _timeout):
        calls.append(json.loads(payload)['operation'])
        return HostRunnerResponse(ok=False, failure={'code':'invalid_output','message':'redeploy host', 'invocation_started': False}).model_dump_json().encode()
    provider = HostRunnerContentProvider(CodexProviderConfig(), GenerationCacheRepository(database.session_factory), transport=transport)
    with pytest.raises(ProviderValidationError, match='before invocation: redeploy host'):
        provider.generate_package(request())
    with database.session_factory() as session:
        assert session.scalar(select(func.count()).select_from(GenerationCacheRecord)) == 0
    assert calls == ['PreflightContentV1']
    database.dispose()


def test_scheduler_preserves_voice_format_and_supported_prompt():
    config = CodexProviderConfig(prompt_template_version=skills.SKILL_TEMPLATE, default_channel_identity='engineering', voice_profiles={'engineering':'Practical engineer voice. No hype.'})
    topic = SimpleNamespace(title='Review scripts', notes='Review exact scripts.', options={'aspect_ratio':'9:16'})
    schedule = SimpleNamespace(options={})
    value = request_from_topic(topic, schedule, config)
    assert value.channel_identity == 'engineering' and value.channel_voice_profile.startswith('Practical')
    assert value.target_duration_seconds == 45 and value.prompt_version == skills.SKILL_TEMPLATE
    assert 'This is a YouTube Short' in build_content_prompt(value, template_version=value.prompt_version, max_chars=60000)
    topic.options = {'aspect_ratio':'16:9', 'duration_seconds':120, 'channel_identity':'unknown'}
    value = request_from_topic(topic, schedule, config)
    assert value.channel_voice_profile == skills.DEFAULT_VOICE
    assert 'This is a YouTube Short' not in build_content_prompt(value, template_version=value.prompt_version, max_chars=60000)


def test_signed_in_api_reviews_skill_reports_and_profile(tmp_path):
    settings = Settings(app=AppConfig(name="test", environment="test"), database=DatabaseConfig(url=f'sqlite:///{tmp_path}/studio.db'), auth=AuthConfig(enabled=True, secure_cookies=False))
    settings.pipeline.video_generation.presets['shorts'] = VideoPresetConfig(duration_seconds=45, minimum_duration_seconds=30, maximum_duration_seconds=55, aspect_ratio='9:16')
    settings.pipeline.codex.prompt_template_version = skills.SKILL_TEMPLATE
    settings.pipeline.codex.voice_profiles = {'engineering':'Practical engineer voice.'}
    settings.pipeline.voice.artifact_root = tmp_path / 'artifacts'
    app = create_app(settings)
    Base.metadata.create_all(app.state.runtime.database.engine)
    app.state.runtime.auth.create_admin('operator', 'a-long-test-password')
    with TestClient(app) as client:
        assert client.get('/api/content-profiles').status_code == 401
        assert client.post('/login', json={'username':'operator','password':'a-long-test-password'}).status_code == 200
        client.headers['x-csrf-token'] = client.cookies['tubeforge_csrf']
        assert any(p['identity']=='engineering' for p in client.get('/api/content-profiles').json()['profiles'])
        created = client.post('/api/videos', json={'title':'Review scripts', 'notes':['Review exact scripts.'], 'preset':'shorts', 'channel_identity':'engineering'})
        assert created.status_code == 201, created.text
        job_id = created.json()['id']
        assert app.state.runtime.jobs.get(job_id).request.channel_voice_profile == 'Practical engineer voice.'
        artifact = tmp_path / 'package.json'
        artifact.write_text(package().model_dump_json())
        app.state.runtime.artifacts.save(Artifact(job_id, JobState.CONTENT_GENERATING, 'content_package', str(artifact), 'c'*64, {}))
        response = client.get(f'/api/jobs/{job_id}/script')
        assert response.status_code == 200 and response.json()['skill_checks']['tools_executed'] == ['hookscore.py','title.py']
        html = client.get('/').text
        assert 'Channel voice profile' in html and 'skillReview' in html
        assert 'Saving schedule…' in html and 'channel_identity:channelSelect.value' in html
        scheduled = client.post('/api/schedules', json={'name':'Engineering Shorts', 'cron':'0 9 * * *', 'options':{'channel_identity':'engineering', 'aspect_ratio':'9:16', 'duration_seconds':45}})
        assert scheduled.status_code == 201
        assert client.get('/api/schedules').json()[0]['options']['channel_identity'] == 'engineering'


def test_real_local_tools_in_host_invocation_record_provenance(monkeypatch, tmp_path):
    import subprocess
    from tubeforge import host_codex_runner as runner
    from tubeforge.providers.content.host_runner_protocol import GenerateShortsScriptRequest
    value = package()
    calls = []
    monkeypatch.setattr(runner, 'bubblewrap_args', lambda _workspace: ['fixed-codex-command'])
    def model_output(command, **kwargs):
        calls.append(command)
        assert all(f'RESOURCE {name}/SKILL.md' in kwargs['input'].decode() for name in skills.RESOURCES)
        output = next((tmp_path / 'outputs').glob('*/content-package.schema.json')).with_name('content-package.json')
        output.write_text(json.dumps({'status':'ready','package':value.model_dump(mode='json'),'reason':None}))
        return subprocess.CompletedProcess(command, 0, b'{"usage":{"input_tokens":123}}\n', b'')
    monkeypatch.setattr(runner.subprocess, 'run', model_output)
    result = runner.run_request(GenerateShortsScriptRequest(request=value.request), root=tmp_path)
    assert len(calls) == 1
    assert result.provenance['youtube_skills']['tools_executed'] == ['hookscore.py', 'title.py']
    assert result.provenance['youtube_skills']['resource_hashes'] == skills.preflight()
    assert result.package['metadata'] == value.model_dump(mode='json')['metadata']


def test_scoring_selects_a_suitable_hook_without_rewriting_other_beats():
    value = package()
    original = value.script_sections[0].narration
    weak = value.hook_options[3]
    changed = value.model_copy(update={'script_sections': (value.script_sections[0].model_copy(update={'narration': weak + original[len(value.hook_options[0]):]}), *value.script_sections[1:])})
    selected, report = skills.select_hook(changed)
    assert selected.script_sections[0].narration.startswith(value.hook_options[0])
    assert selected.script_sections[1:] == changed.script_sections[1:]
    assert selected.metadata == changed.metadata and selected.scene_plans == changed.scene_plans
    assert report['hook_selection']['model_choice'] == weak
    assert len(report['hook_selection']['finalists']) == 2


def test_legacy_exhausted_allowance_survives_default_voice_fields(tmp_path):
    import hashlib
    import sqlite3
    from datetime import UTC, datetime
    from tubeforge import host_codex_runner as runner
    from tubeforge.db.repositories import GenerationExhausted
    from tubeforge.providers.content.host_runner_protocol import GenerateShortsScriptRequest
    value = request().model_copy(update={'prompt_version':'m6-content-v4'})
    legacy = value.model_dump(mode='json')
    legacy.pop('channel_identity'); legacy.pop('channel_voice_profile')
    old_envelope = {'operation':'GenerateShortsScriptV1','request':legacy}
    old_digest = hashlib.sha256(json.dumps(old_envelope,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
    with sqlite3.connect(tmp_path / 'invocations.sqlite3') as connection:
        connection.execute('CREATE TABLE invocations (request_hash TEXT PRIMARY KEY, count INTEGER NOT NULL)')
        connection.execute('INSERT INTO invocations VALUES (?,2)', (old_digest,))
    with pytest.raises(runner.AllowanceExhaustedError):
        runner.consume_invocation(GenerateShortsScriptRequest(request=value), tmp_path)
    material = {'model':'model','normalized_request':legacy,'prompt_version':value.prompt_version,'provider':'host-codex-runner'}
    expected = hashlib.sha256(json.dumps(material,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()
    assert GenerationCacheRepository.cache_key(value,'host-codex-runner','model',value.prompt_version) == expected
    database = create_database(DatabaseConfig(url=f'sqlite:///{tmp_path}/cache.db'))
    Base.metadata.create_all(database.engine)
    cache = GenerationCacheRepository(database.session_factory)
    now = datetime.now(UTC)
    reservation = cache.reserve_or_get(value,'host-codex-runner','model',value.prompt_version,now=now,reservation_seconds=100)
    assert reservation.cache_key == expected
    assert cache.consume_invocation(reservation,maximum=2,now=now)
    assert cache.consume_invocation(reservation,maximum=2,now=now)
    cache.release_after_invocation_failure(reservation,maximum=2,failure={'reason':'previously exhausted'},now=now)
    assert isinstance(cache.reserve_or_get(value,'host-codex-runner','model',value.prompt_version,now=now,reservation_seconds=100),GenerationExhausted)
    assert GenerationCacheRepository.cache_key(value.model_copy(update={'channel_identity':'engineering'}),'host-codex-runner','model',value.prompt_version) != expected
    database.dispose()


def test_rejected_host_draft_is_retained_without_acceptance(tmp_path):
    database = create_database(DatabaseConfig(url=f'sqlite:///{tmp_path}/cache.db'))
    Base.metadata.create_all(database.engine)
    draft = package().model_dump(mode='json')
    draft['script_sections'][-1]['narration'] = 'The title and thumbnail form a pair.'
    def transport(_path, payload, _timeout):
        if json.loads(payload)['operation'] == 'PreflightContentV1':
            result = HostRunnerSuccess(package={}, provenance={'resource_hashes':skills.preflight(),'prompt_sha256':__import__('tubeforge.providers.content.prompts',fromlist=['prompt_evidence']).prompt_evidence(build_content_prompt(request(),template_version=skills.SKILL_TEMPLATE,max_chars=60000))['prompt_sha256']})
        else:
            result = HostRunnerSuccess(package=draft, provenance={'model':'fixed-host-model'})
        return HostRunnerResponse(ok=True, result=result).model_dump_json().encode()
    provider = HostRunnerContentProvider(CodexProviderConfig(), GenerationCacheRepository(database.session_factory), transport=transport)
    with pytest.raises(ProviderValidationError, match='six script sections'):
        provider.generate_package(request())
    with database.session_factory() as session:
        record = session.scalar(select(GenerationCacheRecord))
        assert record.invocation_count == 1 and record.package_json is None
        assert json.loads(record.failure_json)['rejected_result']['package'] == draft
    database.dispose()
