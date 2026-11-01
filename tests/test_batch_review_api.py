import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from tubeforge.api.app import create_app
from tubeforge.batch_plans import BatchShort
from tubeforge.core.config import AppConfig, AuthConfig, DatabaseConfig, Settings
from tubeforge.db.batch_plans import BatchPlanRepository
from tubeforge.db.models import Base, TopicRecord
from tubeforge.db.repositories import Artifact
from tubeforge.db.session import create_database
from tubeforge.domain.contracts import ContentRequest, SourceReference
from tubeforge.domain.states import JobState


@pytest.fixture
def review(tmp_path):
    settings = Settings(app=AppConfig(name='test', environment='test'), database=DatabaseConfig(url=f"sqlite:///{tmp_path / 'review.db'}"), auth=AuthConfig(enabled=True))
    db = create_database(settings.database)
    Base.metadata.create_all(db.engine)
    with TestClient(create_app(settings)) as client:
        runtime = client.app.state.runtime
        runtime.auth.create_admin('operator', 'correct-horse-battery-staple')
        assert client.get('/api/batch-plans/review').status_code == 401
        client.post('/login', json={'username': 'operator', 'password': 'correct-horse-battery-staple'})
        repo = BatchPlanRepository(runtime.database.session_factory)
        repo.import_shorts([BatchShort(id='one', title='One', concept='Concept', beats=[{'t': 0, 'point': 'Hook'}], publish_at='2026-11-01T10:00:00+05:30')], commit=True)
        request = ContentRequest(topic='One', angle='Concept', target_duration_seconds=60, language='en', audience='general', prompt_version='test-v1', sources=(SourceReference(source_id='operator', url='https://local.invalid/notes', title='Unverified notes'),))
        job_id = repo.produce(['one'], lambda short: request)[0]['job_id']
        runtime.jobs.update_state(job_id, JobState.FINAL_READY)
        for name, stage, content in [('final', JobState.FINAL_RENDERING, b'stub final bytes'), ('content_package', JobState.CONTENT_GENERATING, b'{"script_sections": []}'), ('thumbnail', JobState.PUBLICATION_PREPARING, b'stub thumbnail')]:
            path = tmp_path / name
            path.write_bytes(content)
            checksum = hashlib.sha256(content).hexdigest()
            runtime.artifacts.save(Artifact(job_id, stage, name, str(path), checksum, {}))
        with runtime.database.session_factory.begin() as session:
            row = session.get(TopicRecord, 'batch-one')
            options = json.loads(row.options_json)
            options['batch_qa'] = {'exit_code': 0, 'output': 'stub checker PASS', 'artifact_checksum': hashlib.sha256(b'stub final bytes').hexdigest()}
            row.options_json = json.dumps(options)
        yield client, runtime, repo, job_id, tmp_path
    db.dispose()


def snapshot(client):
    return client.get('/api/batch-plans/review').json()[0]


def action(client, name, identity):
    return client.post('/api/batch-plans/one/review', json={'action': name, 'reviewed_identity': identity})


def csrf(client):
    client.headers['x-csrf-token'] = client.cookies['tubeforge_csrf']


def test_signed_in_review_approve_ready_reject_and_checksum_mismatch(review):
    client, runtime, repo, job_id, root = review
    page = client.get('/batch/review')
    assert page.status_code == 200
    for text in ['Day review', 'Approve', 'Reject', 'Regenerate', 'Stage as ready', 'aria-live', 'video.controls=true', 'if(!busy)refresh(false)', 'The selected artifact changed']:
        assert text in page.text
    current = snapshot(client)
    identity = current['reviewed_identity']
    assert current['state'] == 'needs_review' and current['qa_ok']
    assert current['thumbnail_url'] and current['preview_url'] and current['script'] is not None
    assert client.get('/api/batch-plans/review?day=2026-11-02').json() == []
    assert len(client.get('/api/batch-plans/review?day=2026-11-01').json()) == 1
    assert action(client, 'approve', identity).status_code == 403
    csrf(client)
    assert action(client, 'ready', identity).status_code == 409
    assert action(client, 'approve', '0' * 64).status_code == 409
    assert action(client, 'approve', identity).json()['state'] == 'approved'
    assert action(client, 'ready', identity).json()['state'] == 'ready'
    assert runtime.jobs.get(job_id).state == JobState.FINAL_READY
    assert action(client, 'reject', identity).json()['decision'] == 'rejected'
    assert snapshot(client)['state'] == 'needs_review'
    assert action(client, 'ready', identity).status_code == 409
    (root / 'final').write_bytes(b'changed bytes')
    assert action(client, 'approve', identity).status_code == 409
    assert snapshot(client)['state'] == 'needs_review'
    assert not snapshot(client)['available']


def test_regenerate_is_atomic_idempotent_and_requires_new_approval(review):
    client, runtime, repo, original, root = review
    csrf(client)
    identity = snapshot(client)['reviewed_identity']
    assert action(client, 'approve', identity).status_code == 200
    response = action(client, 'regenerate', identity)
    assert response.status_code == 200, response.text
    child = response.json()['job_id']
    assert child != original
    assert runtime.jobs.get(child).request == runtime.jobs.get(original).request
    assert runtime.jobs.get(child).request.review_mode == 'manual'
    assert action(client, 'regenerate', identity).json()['action'] == 'skipped'
    assert len(runtime.jobs.list_recent()) == 2
    assert len(repo.list()) == 1
    assert snapshot(client)['state'] == 'needs_review'
    assert not snapshot(client)['available']
    assert action(client, 'ready', identity).status_code == 409
    assert repo.for_job(original)['batch_history']
    assert runtime.jobs.claim_oldest_eligible('test', now=datetime.now(UTC), lease_seconds=30).id == child
    events = runtime.events.list_for_job(original)
    assert any(e.event_type == 'batch_review_regenerate' for e in events)


def test_review_rejects_qa_for_different_video_and_stale_script(review):
    client, runtime, repo, job_id, root = review
    csrf(client)
    identity = snapshot(client)['reviewed_identity']
    with runtime.database.session_factory.begin() as session:
        row = session.get(TopicRecord, 'batch-one')
        options = json.loads(row.options_json)
        options['batch_qa']['artifact_checksum'] = '0' * 64
        row.options_json = json.dumps(options)
    assert action(client, 'approve', identity).status_code == 409
    assert action(client, 'reject', identity).status_code == 200
    (root / 'content_package').write_text('{"changed":true}')
    assert action(client, 'regenerate', identity).status_code == 409


def test_review_javascript_saves_confirmed_transitions_and_keeps_player(review):
    from test_batch_ui_runtime import runtime
    client, backend, repo, job_id, root = review
    context, run = runtime(client, client.get('/batch/review').text)
    run('list.children[0].children[0].onclick()')
    context.eval('globalThis.originalPlayer=detail.children.find(x=>x.tagName==="video")')
    run('refresh(false)')
    assert context.eval('detail.children.includes(originalPlayer)')
    run('detail.querySelectorAll("#actions button")[0].onclick()')
    assert snapshot(client)['state'] == 'approved'
    assert context.eval('notice.textContent.includes("Saved: approved")')
    run('detail.querySelectorAll("#actions button")[3].onclick()')
    assert snapshot(client)['state'] == 'ready'
    run('detail.querySelectorAll("#actions button")[1].onclick()')
    assert snapshot(client)['decision'] == 'rejected'


def test_regeneration_cannot_reset_exhausted_two_attempt_allowance(review):
    from tubeforge.db.repositories import GenerationCacheRepository, GenerationExhausted
    client, runtime, repo, original, root = review
    csrf(client)
    cache = GenerationCacheRepository(runtime.database.session_factory)
    request = runtime.jobs.get(original).request
    now = datetime.now(UTC)
    reservation = cache.reserve_or_get(request, 'stub', 'stub-model', 'test-v1', now=now, reservation_seconds=60)
    assert cache.consume_invocation(reservation, maximum=2, now=now)
    assert cache.consume_invocation(reservation, maximum=2, now=now)
    assert cache.release_after_invocation_failure(reservation, maximum=2, failure={'reason':'stub rejected'}, now=now)
    response = action(client, 'regenerate', snapshot(client)['reviewed_identity'])
    assert response.status_code == 200
    child = runtime.jobs.get(response.json()['job_id'])
    assert isinstance(cache.reserve_or_get(child.request, 'stub', 'stub-model', 'test-v1', now=now, reservation_seconds=60), GenerationExhausted)


def test_review_javascript_disables_stale_artifact_without_replacing_player(review):
    from test_batch_ui_runtime import runtime
    client, backend, repo, job_id, root = review
    context, run = runtime(client, client.get('/batch/review').text)
    run('list.children[0].children[0].onclick()')
    context.eval('globalThis.originalPlayer=detail.children.find(x=>x.tagName==="video")')
    (root / 'final').write_bytes(b'changed since the review opened')
    run('refresh(false)')
    assert context.eval('detail.children.includes(originalPlayer)')
    assert context.eval('detail.querySelectorAll("#actions button").every(x=>x.disabled)')
    assert context.eval('notice.textContent.includes("artifact changed")')
