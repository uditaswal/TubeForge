import hashlib
import json
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from PIL import Image
from sqlalchemy import delete, select
from test_batch_review_api import review
from tubeforge.db.models import ArtifactRecord, TopicRecord
from tubeforge.workers.batch_thumbnail import ensure_thumbnail


@pytest.mark.parametrize('planned,expected', [('Plan wins', 'Plan wins'), ('', 'Generated option')])
def test_thumbnail_registered_reviewed_text_precedence_and_idempotency(review, monkeypatch, planned, expected):
    client, runtime, repo, job_id, root = review
    with runtime.database.session_factory.begin() as session:
        session.execute(delete(ArtifactRecord).where(ArtifactRecord.job_id == job_id, ArtifactRecord.name == 'thumbnail'))
        row = session.get(TopicRecord, 'batch-one')
        options = json.loads(row.options_json)
        options['batch_plan']['thumbnail']['text'] = planned
        options['batch_plan']['thumbnail']['visual'] = 'Never fetch https://example.invalid/image'
        row.options_json = json.dumps(options)
        package = session.scalar(select(ArtifactRecord).where(ArtifactRecord.job_id == job_id, ArtifactRecord.name == 'content_package'))
        content = json.dumps({'thumbnail_brief': {'text_options': ['Generated option']}}).encode()
        (root / 'content_package').write_bytes(content)
        package.checksum_sha256 = hashlib.sha256(content).hexdigest()
    runtime.jobs.claim_oldest_eligible('thumb', now=datetime.now(UTC), lease_seconds=300)
    calls = []
    def compose(frame, text):
        calls.append(text)
        assert frame is None
        return Image.new('RGB', (1080, 1920), '#123456'), {}
    monkeypatch.setattr('tubeforge.pipeline.thumbnail.compose_portrait', compose)
    guard = SimpleNamespace(check=lambda **kwargs: True)
    ensure_thumbnail(runtime.database.session_factory, job_id, root, 'thumb', guard)
    ensure_thumbnail(runtime.database.session_factory, job_id, root, 'thumb', guard)
    assert calls == [expected]
    runtime.jobs.release_claim(job_id, 'thumb')
    result = client.get('/api/batch-plans/review').json()[0]
    assert result['thumbnail_url']
    assert result['thumbnail_result']['text'] == expected
    artifact = next(a for a in runtime.artifacts.list_for_job(job_id) if a.name == 'thumbnail')
    with Image.open(artifact.path) as image:
        assert image.size == (1080, 1920)
    assert str(root / job_id) in artifact.path
    assert client.get(result['thumbnail_url']).status_code == 200


def test_thumbnail_failure_preserves_video_and_exposes_reason(review, monkeypatch):
    client, runtime, repo, job_id, root = review
    with runtime.database.session_factory.begin() as session:
        session.execute(delete(ArtifactRecord).where(ArtifactRecord.job_id == job_id, ArtifactRecord.name == 'thumbnail'))
        row = session.get(TopicRecord, 'batch-one')
        options = json.loads(row.options_json)
        options['batch_plan']['thumbnail']['text'] = 'Plan text'
        row.options_json = json.dumps(options)
    runtime.jobs.claim_oldest_eligible('thumb', now=datetime.now(UTC), lease_seconds=300)
    def fail(*args, **kwargs):
        raise OSError('stub font failure')
    monkeypatch.setattr('tubeforge.pipeline.thumbnail.compose_portrait', fail)
    ensure_thumbnail(runtime.database.session_factory, job_id, root, 'thumb', SimpleNamespace(check=lambda **kwargs: True))
    runtime.jobs.release_claim(job_id, 'thumb')
    result = client.get('/api/batch-plans/review').json()[0]
    assert result['production_state'] == 'final_ready'
    assert result['state'] == 'needs_review'
    assert 'stub font failure' in result['thumbnail_result']['reason']
    assert result['thumbnail_url'] is None
