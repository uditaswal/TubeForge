from pathlib import Path
from fastapi.testclient import TestClient
from tubeforge.api.app import create_app
from tubeforge.core.config import AppConfig, AuthConfig, DatabaseConfig, Settings
from tubeforge.db.models import Base, TopicRecord
from tubeforge.db.session import create_database

PLAN = '## One\n```yaml\nid: one\ntitle: One\nconcept: Explain one\nbeats: [{t: 0, point: Hook}]\n```\n'


def test_signed_in_import_preview_commit_idempotency_and_conflict(tmp_path: Path):
    settings = Settings(app=AppConfig(name='test', environment='test'), database=DatabaseConfig(url=f"sqlite:///{tmp_path / 'batch.db'}"), auth=AuthConfig(enabled=True))
    database = create_database(settings.database)
    Base.metadata.create_all(database.engine)
    with TestClient(create_app(settings)) as client:
        runtime = client.app.state.runtime
        runtime.auth.create_admin('operator', 'correct-horse-battery-staple')
        assert client.get('/api/batch-plans').status_code == 401
        assert client.post('/api/batch-plans/import', json={'markdown': PLAN}).status_code == 401
        assert client.post('/login', json={'username': 'operator', 'password': 'correct-horse-battery-staple'}).status_code == 200
        assert client.post('/api/batch-plans/import', json={'markdown': PLAN}).status_code == 403
        client.headers['x-csrf-token'] = client.cookies['tubeforge_csrf']
        page = client.get('/batch')
        assert page.status_code == 200
        for value in ['batchFile', 'Validate and preview', 'Commit import', 'aria-live', 'disabled', 'x-csrf-token']:
            assert value in page.text
        preview = client.post('/api/batch-plans/import', json={'markdown': PLAN}).json()
        assert preview['items'][0]['action'] == 'created'
        assert client.get('/api/batch-plans').json() == []
        def commit(plan):
            response = client.post('/api/batch-plans/import', json={'markdown': plan, 'commit': True})
            assert response.status_code == 200, response.text
            return response.json()['items'][0]['action']
        assert commit(PLAN) == 'created'
        assert commit(PLAN) == 'skipped'
        changed = PLAN.replace('title: One', 'title: Changed')
        assert commit(changed) == 'updated'
        with runtime.database.session_factory.begin() as session:
            row = session.get(TopicRecord, 'batch-one')
            row.status = 'generating'
        assert commit(PLAN) == 'conflict'
        assert client.get('/api/batch-plans').json()[0]['short']['title'] == 'Changed'
        assert client.post('/api/batch-plans/import', json={'markdown': PLAN.replace('id: one\n', ''), 'commit': True}).status_code == 422
    database.dispose()
