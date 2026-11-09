"""Batch plans page: stage chips, day-grouped cards, drop zone and inline line-numbered errors."""
import json
import pytest

from tubeforge.api.batch_stage import STAGES, stage_for


@pytest.mark.parametrize('job_state,review,expected', [
    (None, None, 'imported'),
    ('content_generating', None, 'scripting'),
    ('script_approval_required', None, 'needs_review'),
    ('voice_generation', None, 'rendering'),
    ('final_rendering', None, 'rendering'),
    ('preview_ready', None, 'needs_review'),
    ('final_ready', None, 'needs_review'),
    ('final_ready', 'approved', 'approved'),
    ('final_ready', 'ready', 'ready'),
    ('failed_validation', 'approved', 'attention'),
    ('needs operator decision', None, 'attention'),
    ('cancelled', None, 'attention'),
])
def test_stage_for(job_state, review, expected):
    assert stage_for(job_state, review) == expected
    assert expected in STAGES or expected == 'attention'


def _client(tmp_path):
    from fastapi.testclient import TestClient
    from tubeforge.api.app import create_app
    from tubeforge.core.config import AppConfig, AuthConfig, DatabaseConfig, Settings
    from tubeforge.db.models import Base
    from tubeforge.db.session import create_database
    settings = Settings(app=AppConfig(name='test', environment='test'), database=DatabaseConfig(url=f"sqlite:///{tmp_path / 'cards.db'}"), auth=AuthConfig(enabled=True))
    db = create_database(settings.database)
    Base.metadata.create_all(db.engine)
    return TestClient(create_app(settings)), db


def _plan(*items):
    return ''.join(f'## {i}\n```yaml\nid: {i}\ntitle: Title {i}\nconcept: Concept\npublish_at: {d}\nbeats: [{{t: 0, point: Hook}}]\n```\n' for i, d in items)


def test_list_carries_stage_and_thumbnail_fields(tmp_path):
    client, db = _client(tmp_path)
    with client:
        client.app.state.runtime.auth.create_admin('operator', 'correct-horse-battery-staple')
        client.post('/login', json={'username': 'operator', 'password': 'correct-horse-battery-staple'})
        csrf = client.cookies.get('tubeforge_csrf', '')
        r = client.post('/api/batch-plans/import', headers={'x-csrf-token': csrf}, json={'markdown': _plan(('one', '2026-11-04T09:00:00+00:00')), 'commit': True, 'plan_id': 'default'})
        assert r.status_code == 200, r.text
        item = client.get('/api/batch-plans').json()[0]
        assert item['stage'] == 'imported' and item['thumbnail_url'] is None
    db.dispose()


def test_page_has_drop_zone_error_list_and_day_groups(tmp_path):
    pytest.importorskip('quickjs')
    from tests.test_batch_ui_runtime import runtime
    client, db = _client(tmp_path)
    with client:
        client.app.state.runtime.auth.create_admin('operator', 'correct-horse-battery-staple')
        client.post('/login', json={'username': 'operator', 'password': 'correct-horse-battery-staple'})
        html = client.get('/batch').text
        assert 'id="dropZone"' in html and 'id="importErrors"' in html and '<table' not in html
        context, run = runtime(client, html)
        context.eval('display(' + json.dumps([
            {'short': {'id': 'a', 'title': 'A', 'publish_at': '2026-11-05T09:00:00+00:00', 'length_s': 60}, 'status': 'imported', 'job_id': None, 'stage': 'imported', 'qa': None, 'thumbnail_url': None},
            {'short': {'id': 'b', 'title': 'B', 'publish_at': '2026-11-04T09:00:00+00:00', 'length_s': 60}, 'status': 'final_ready', 'job_id': 'j', 'stage': 'approved', 'qa': {'exit_code': 0}, 'thumbnail_url': '/api/jobs/j/artifacts/thumbnail'},
            {'short': {'id': 'c', 'title': 'C', 'length_s': 45}, 'status': 'failed_validation', 'job_id': 'k', 'stage': 'attention', 'qa': None, 'thumbnail_url': None},
        ]) + ')')
        out = context.eval('rows.innerHTML')
        assert out.index('data-day="2026-11-04"') < out.index('data-day="2026-11-05"') < out.index('data-day="Unassigned"')
        assert 'src="/api/jobs/j/artifacts/thumbnail"' in out and 'No thumbnail' in out
        assert 'class="done"' in out and 'aria-current="step">Approved' in out and 'Needs attention' in out
        # invalid plan: inline line-numbered errors, nothing committed
        context.eval('input.value="## Bad\\n```yaml\\nid: Bad Id\\n```\\n";input.oninput()')
        run('submit(false)')
        assert context.eval('errorsEl.hidden') is False
        assert context.eval('errorsEl.innerHTML.includes("data-line")') or context.eval('errorsEl.innerHTML.includes("Plan")')
        assert context.eval('result.textContent.includes("Nothing was saved")')
        context.eval('input.oninput()')
        assert context.eval('errorsEl.hidden') is True
        assert client.get('/api/batch-plans').json() == []
        assert 'id="safetyWarnings"' in html
        run('loadSafety()')
        assert 'No repetition or cadence warnings' in context.eval('setting("safetySummary").textContent')
    db.dispose()


def test_stale_saved_approval_is_not_shown_as_approved(tmp_path):
    """A saved 'approved' whose reviewed identity no longer matches must not light the Approved chip."""
    import json as _json
    from sqlalchemy import select
    from tubeforge.db.models import PipelineJobRecord, TopicRecord
    client, db = _client(tmp_path)
    with client:
        client.app.state.runtime.auth.create_admin('operator', 'correct-horse-battery-staple')
        client.post('/login', json={'username': 'operator', 'password': 'correct-horse-battery-staple'})
        csrf = client.cookies.get('tubeforge_csrf', '')
        client.post('/api/batch-plans/import', headers={'x-csrf-token': csrf}, json={'markdown': _plan(('one', '2026-11-04T09:00:00+00:00')), 'commit': True, 'plan_id': 'default'})
        runtime = client.app.state.runtime
        with runtime.database.session_factory() as session:
            topic = session.scalar(select(TopicRecord).where(TopicRecord.id.like('batch-%')))
            options = _json.loads(topic.options_json)
            options['batch_review'] = {'state': 'approved', 'decision': 'approved', 'identity': 'stale-identity'}
            topic.options_json = _json.dumps(options)
            session.commit()
        item = client.get('/api/batch-plans').json()[0]
        assert item['stage'] == 'imported' and item['review_state'] is None
    db.dispose()


def test_dangling_job_reference_does_not_break_the_list(tmp_path):
    """Real data had nine topics whose generation was deleted; GET /api/batch-plans returned 500 for the whole page."""
    import json as _json
    from sqlalchemy import select
    from tubeforge.db.models import TopicRecord
    client, db = _client(tmp_path)
    with client:
        client.app.state.runtime.auth.create_admin('operator', 'correct-horse-battery-staple')
        client.post('/login', json={'username': 'operator', 'password': 'correct-horse-battery-staple'})
        csrf = client.cookies.get('tubeforge_csrf', '')
        client.post('/api/batch-plans/import', headers={'x-csrf-token': csrf}, json={'markdown': _plan(('one', '2026-11-04T09:00:00+00:00'), ('two', '2026-11-04T10:00:00+00:00')), 'commit': True, 'plan_id': 'default'})
        with client.app.state.runtime.database.session_factory() as session:
            topic = session.scalars(select(TopicRecord).where(TopicRecord.id.like('batch-%'))).first()
            topic.generation_job_id = 'batch-deleted-job'
            session.commit()
        response = client.get('/api/batch-plans')
        assert response.status_code == 200
        by_id = {i['short']['id']: i for i in response.json()}
        gone = next(i for i in by_id.values() if i['job_id'] == 'batch-deleted-job')
        assert gone['status'] == 'job missing' and gone['stage'] == 'attention' and gone['qa'] is None
        assert any(i['stage'] == 'imported' for i in by_id.values())
    db.dispose()
