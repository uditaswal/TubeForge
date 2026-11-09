"""Signed-in LF2 API tests using the real worker and synthetic host receipts."""
from contextlib import contextmanager
import hashlib
import json

from fastapi.testclient import TestClient
import pytest

from tubeforge.api.app import create_app
from tubeforge.core.config import AppConfig, AuthConfig, DatabaseConfig, Settings
from tubeforge.reference.extractor import YoutubeReferenceExtractor
from test_api_workflow import _migrate
from test_long_form_service import workflow
from test_long_form_writing import writing_inputs
from test_reference_intake_extractor import FixtureHTTP, URL


@contextmanager
def review_app(tmp_path):
    mock_root = tmp_path / 'mock-host'
    mock_root.mkdir()
    mock_workflow = workflow.__wrapped__(mock_root)
    mock_service, _, _, mock_state, client = next(mock_workflow)
    db = tmp_path / 'review.db'
    _migrate(db)
    settings = Settings(
        app=AppConfig(name='LF2 review test', environment='test'),
        database=DatabaseConfig(url=f'sqlite:///{db}'), auth=AuthConfig(enabled=True),
    )
    settings.pipeline.codex.model = 'fixture-model'
    app = create_app(settings)
    runtime = app.state.runtime
    runtime.auth.create_admin('script-reviewer', 'test-only-script-password')
    caption = {'events': [{'tStartMs': 0, 'dDurationMs': 4000, 'segs': [{'utf8': 'Synthetic reference text only.'}]}]}
    runtime.reference_intakes.extractor = YoutubeReferenceExtractor(FixtureHTTP(captions=json.dumps(caption).encode()))
    runtime.long_form_writing.client = client
    runtime.long_form_writing.source_capture = mock_service.source_capture
    try:
        yield app, runtime, mock_state
    finally:
        next(mock_workflow, None)


@pytest.fixture
def signed_in(tmp_path):
    with review_app(tmp_path) as (app, runtime, state), TestClient(app) as client:
        assert client.post('/login', json={'username': 'script-reviewer', 'password': 'test-only-script-password'}).status_code == 200
        headers = {'x-csrf-token': client.cookies.get('tubeforge_csrf')}
        yield client, runtime, state, headers


def ready_brief(client, runtime, headers):
    capture = client.post('/api/reference-intakes', json={'reference_url': URL, 'target_duration_seconds': 600}, headers=headers)
    assert capture.status_code == 201
    ref = capture.json()['intake']
    runtime.reference_intakes.run_once('reference-fixture')
    request = writing_inputs()[0].request
    return dict(intake_id=ref['intake_id'], intake_revision=ref['revision'], topic=request.topic, angle=request.angle, audience=request.audience)


def test_signed_in_review_preserves_exact_bundle_and_never_queues_render(signed_in):
    client, runtime, state, headers = signed_in
    brief = ready_brief(client, runtime, headers)
    assert 'Long-form scripts' in client.get('/long-form').text
    assert client.post('/api/long-form', json=brief).status_code == 403
    created = client.post('/api/long-form', json=brief, headers=headers)
    assert created.status_code == 201, created.text
    run = created.json()
    path = '/api/long-form/' + run['id']
    assert run['state'] == 'pending' and not state['launches']
    assert 'draft' not in client.get('/api/long-form').json()['items'][0]
    assert client.post('/api/long-form', json=brief, headers=headers).json()['id'] == run['id']
    for _ in range(3):
        runtime.long_form_writing.run_once('script-fixture')
    run = client.get(path).json()
    assert run['state'] == 'awaiting_review', run['message']
    assert state['launches'] == ['research', 'draft', 'review']
    assert run['review_applies_to_current_draft'] and not run['decisions']
    decision = {'decision': 'approved', 'review_identity': run['review_identity'], 'reviewed_evidence': True}
    assert client.post(path + '/decision', json=decision).status_code == 403
    assert client.post(path + '/decision', json={**decision, 'review_identity': run['draft_sha256']}, headers=headers).status_code == 409
    assert client.post(path + '/decision', json={**decision, 'reviewed_evidence': False}, headers=headers).status_code == 422
    assert client.get(path + '/export', params={'review_identity': '0'*64}).status_code == 409
    exported = client.get(path + '/export', params={'review_identity': run['review_identity']})
    assert exported.status_code == 200
    assert exported.headers['etag'].strip('"') == hashlib.sha256(exported.content).hexdigest()
    assert exported.json()['preparation']['review_identity'] == run['review_identity']
    approved = client.post(path + '/decision', json=decision, headers=headers)
    assert approved.status_code == 200, approved.text
    assert approved.json()['state'] == 'approved'
    assert approved.json()['decisions'][0]['actor'] == 'script-reviewer'
    assert client.post(path + '/decision', json=decision, headers=headers).status_code == 409
    assert client.post(path + '/cancel', headers=headers).status_code == 409
    assert client.get('/api/jobs').json() == []
    client.cookies.clear()
    assert client.get(path).status_code == 401
    assert client.get('/long-form', follow_redirects=False).status_code == 303


def test_invalid_brief_and_normal_job_profile_cannot_dispatch(signed_in):
    client, runtime, state, headers = signed_in
    brief = ready_brief(client, runtime, headers)
    for change in ({'review_identity': '0'*64}, {'owner': 'claude'}, {'model': 'opus'},
                   {'token_policy': {'total_reserved_tokens': 150001}}, {'topic': '  '}):
        assert client.post('/api/long-form', json={**brief, **change}, headers=headers).status_code == 422
    assert client.post('/api/long-form', json={**brief, 'intake_revision': 99}, headers=headers).status_code == 404
    request = writing_inputs()[0].request.model_dump(mode='json')
    assert client.post('/api/jobs', json=request, headers=headers).status_code == 422
    assert client.get('/api/long-form').json()['items'] == []
    assert runtime.long_form_writing.run_once('no-work') is None
    assert not state['launches']


def test_cancel_and_inspect_receipt_do_not_launch_additional_work(signed_in):
    client, runtime, state, headers = signed_in
    brief = ready_brief(client, runtime, headers)
    run = client.post('/api/long-form', json=brief, headers=headers).json()
    path = '/api/long-form/' + run['id']
    assert client.post(path + '/calls/research/receipt', headers=headers).status_code == 409
    runtime.long_form_writing.run_once('script-fixture')
    assert state['launches'] == ['research']
    assert client.post(path + '/calls/research/receipt').status_code == 403
    receipt = client.post(path + '/calls/research/receipt', headers=headers)
    assert receipt.status_code == 200 and receipt.json()['state'] == 'succeeded'
    assert state['launches'] == ['research']
    cancelled = client.post(path + '/cancel', headers=headers).json()
    assert cancelled['state'] == 'cancelled' and cancelled['usage']['reserved_calls'] == 1
    assert runtime.long_form_writing.run_once('no-work') is None


def test_rejected_output_remains_visible_after_recent_activity_rolls_off(signed_in):
    from datetime import UTC, datetime

    from tubeforge.db.models import LongFormWritingEventRecord

    client, runtime, state, headers = signed_in
    brief = ready_brief(client, runtime, headers)
    run = client.post('/api/long-form', json=brief, headers=headers).json()
    state['mode'] = 'first_bad'
    for _ in range(4):
        runtime.long_form_writing.run_once('script-fixture')
    with runtime.long_form_writing.repository.sessions.begin() as session:
        session.add_all(LongFormWritingEventRecord(
            run_id=run['id'], event='fixture_later_event', actor='test',
            details_json='{}', created_at=datetime.now(UTC),
        ) for _ in range(65))
    review = client.get('/api/long-form/' + run['id']).json()
    assert review['state'] == 'awaiting_review'
    assert len(review['activity']) == 60
    assert all(event['event'] == 'fixture_later_event' for event in review['activity'])
    draft = next(call for call in review['calls'] if call['stage'] == 'draft')
    assert draft['draft_outcome']['disposition'] == 'rejected'
    assert draft['draft_outcome']['reason'] == 'writer must return a JSON object'
    assert draft['response']['result']['raw_output'] == '{bad synthetic output'
