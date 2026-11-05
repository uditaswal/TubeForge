import hashlib
import json
from pathlib import Path
import pytest
from tubeforge.pipeline.direction import direction_report
from tubeforge.domain.contracts import ContentPackage
from tubeforge.domain.states import JobState
from test_pipeline_orchestrator import pipeline, request

FIXTURE = Path(__file__).parent/'fixtures/production/docker_images_containers/content_package.json'


def test_report_preserves_narration_cues_and_marks_editorial_history():
    package = ContentPackage.model_validate_json(FIXTURE.read_bytes())
    before = package.model_dump_json()
    context = {'recent_angles':[{'job_id':'previous','topic':package.request.topic,'angle':package.request.angle}]}
    report = direction_report(package, context)
    assert package.model_dump_json() == before
    assert report['layouts_changed'] is False and report['advisory'] is True
    assert report['similar_angles'] == [{'job_id':'previous','similarity':1.0}]
    for row, scene in zip(report['scenes'], package.scene_plans, strict=True):
        expected = next((cue.model_dump(mode='json') for cue in (scene.terminal_cues, scene.card_cues, scene.teaching_cues) if cue is not None), None)
        assert row['reveal_anchors'] == expected
    assert report['scenes'][0]['narration_sha256'] == hashlib.sha256(package.script_sections[0].narration.encode()).hexdigest()
    assert direction_report(package)['history_available'] is False
    shuffled=package.model_copy(update={'scene_plans':tuple(reversed(package.scene_plans))})
    assert direction_report(shuffled)['scenes'] == direction_report(package)['scenes']


def test_channel_history_is_bounded_isolated_and_frozen_before_retry(pipeline):
    runner, content, *_ = pipeline
    old = runner.jobs.create('old', request())
    runner.jobs.create('other-channel', request().model_copy(update={'channel_identity':'other'}))
    job = runner.jobs.create('current', request())
    context = runner._direction_context(job)
    assert [row['job_id'] for row in context['recent_angles']] == [old.id]
    original = job.request.model_dump_json()
    from tubeforge.domain.contracts import generation_request_key_payload
    cache_key=generation_request_key_payload(job.request)
    runner.jobs.create('later', request())
    assert runner._direction_context(job) == context
    assert job.request.model_dump_json() == original and content.calls == 0
    assert generation_request_key_payload(job.request)==cache_key
    assert runner.jobs.recent_channel_angles(job,limit=1) == context['recent_angles']
    artifact = runner.artifacts.get(job.id,JobState.CONTENT_GENERATING,'direction_context')
    Path(artifact.path).write_text('{}')
    with pytest.raises(Exception,match='checkpoint missing or invalid'):runner._direction_context(job)


def test_three_repeated_layouts_require_review_without_random_mutation():
    package = ContentPackage.model_validate_json(FIXTURE.read_bytes())
    scene = package.scene_plans[0]
    scenes = tuple(scene.model_copy(update={'scene_id':s.scene_id}) for s in package.scene_plans)
    package = package.model_copy(update={'scene_plans':scenes})
    report=direction_report(package)
    assert any(w['code']=='adjacent_layout_repetition' for w in report['warnings'])
    assert len({s.visual_type for s in package.scene_plans})==1


def test_signed_in_direction_review_is_read_only_and_missing_history_is_truthful(tmp_path):
    from fastapi.testclient import TestClient
    from tubeforge.api.app import create_app
    from tubeforge.db.repositories import Artifact
    from test_provider_routing_api import settings_for, sign_in
    with TestClient(create_app(settings_for(tmp_path))) as client:
        assert client.get('/api/jobs/sample/script').status_code == 401
        sign_in(client, True)
        runtime=client.app.state.runtime
        package=ContentPackage.model_validate_json(FIXTURE.read_bytes())
        job=runtime.jobs.create('sample',package.request)
        raw=package.model_dump_json().encode(); path=tmp_path/'package.json';path.write_bytes(raw)
        runtime.artifacts.save(Artifact(job.id,JobState.CONTENT_GENERATING,'content_package',str(path),hashlib.sha256(raw).hexdigest(),{}))
        response=client.get('/api/jobs/sample/script')
        assert response.status_code==200
        report=response.json()['direction']
        assert report['advisory'] and not report['history_available'] and not report['layouts_changed']
        assert runtime.artifacts.get(job.id,JobState.CONTENT_GENERATING,'direction_context') is None
        dashboard=client.get('/').text
        assert 'id="sceneDirection"' in dashboard and 'Advisory only; no layouts or approvals changed.' in dashboard


def test_approved_php_revision_binds_exact_parent_copy_sources_and_valid_cues():
    import importlib.util
    from tubeforge.pipeline.scene_contracts import compile_scene_contract
    root=Path(__file__).resolve().parents[1]
    spec=importlib.util.spec_from_file_location('php_m4_benchmark',root/'scripts/benchmark_php_m4.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    fixture=root/'tests/fixtures/benchmarks/php_m4'
    raw=(fixture/'approved_proposal.json').read_bytes();proposal=json.loads(raw)
    approval=json.loads((fixture/'operator-approval.json').read_text())
    assert hashlib.sha256(raw).hexdigest()==approval['proposal_sha256']==module.APPROVED
    package=module.revised_package((fixture/'base_package.json').read_bytes(),proposal)
    assert [s.narration for s in package.script_sections]==proposal['narrations']
    assert len(' '.join(proposal['narrations']).split())==148
    assert 'Black October' not in ' '.join(s.narration for s in package.script_sections)
    assert 'c6' not in {c.claim_id for c in package.claims}
    encoded=package.model_dump_json().encode()
    contract=compile_scene_contract(encoded,(fixture/'source_packet.json').read_bytes(),accepted_script_identity=hashlib.sha256(encoded).hexdigest())
    assert contract.scenes[-1].display_elements==('Internet-facing first','Find PHP systems','Update PHP')
    assert contract.scenes[-1].card_cues.third_word_index<12
    with pytest.raises(ValueError,match='parent package differs'):
        module.revised_package((fixture/'base_package.json').read_bytes()+b' ',proposal)
