"""Staged export of ready batch shorts: atomic, checksum-bound, invalidated by change, no publishing."""
import json
from pathlib import Path

from tests.test_batch_review_api import action, csrf, review, snapshot  # noqa: F401  (pytest fixture)
from tubeforge.batch_export import verify


def stage(client):
    csrf(client)
    identity = snapshot(client)['reviewed_identity']
    assert action(client, 'approve', identity).status_code == 200
    response = action(client, 'ready', identity)
    assert response.status_code == 200, response.text
    return identity


def test_ready_writes_a_verified_export_with_the_reviewed_artifacts(review, monkeypatch):
    client, runtime, repo, job_id, root = review
    monkeypatch.chdir(root)
    csrf(client)
    identity = snapshot(client)['reviewed_identity']
    action(client, 'approve', identity)
    assert snapshot(client)['export'] is None                      # approval alone stages nothing
    stage_identity = stage(client)
    export = snapshot(client)['export']
    assert export['status'] == 'current'
    folder = Path(export['path'])
    assert sorted(p.name for p in folder.iterdir()) == ['final.mp4', 'package.json', 'thumbnail.jpg']
    assert (folder / 'final.mp4').read_bytes() == b'stub final bytes'
    package = json.loads((folder / 'package.json').read_text())
    assert package['published'] is False and package['plan_id'] == 'one' and package['reviewed_identity'] == stage_identity
    assert package['title'] == 'One' and package['publish_at_metadata'].startswith('2026-11-01')
    assert package['checksums']['final'] == package['files']['final.mp4']
    assert package['qa']['exit_code'] == 0
    api = client.get('/api/batch-plans/one/export').json()
    assert api['status'] == 'current' and api['package']['plan_id'] == 'one'
    assert 'Staged export' in client.get('/batch/review').text


def test_re_export_replaces_the_folder_atomically_and_leaves_no_scratch(review, monkeypatch):
    client, runtime, repo, job_id, root = review
    monkeypatch.chdir(root)
    stage(client)
    export_root = Path(snapshot(client)['export']['path']).parent
    identity = snapshot(client)['reviewed_identity']
    assert action(client, 'reject', identity).json()['decision'] == 'rejected'
    stage(client)
    assert [p.name for p in export_root.iterdir()] == ['one-2026-11-01']
    assert snapshot(client)['export']['status'] == 'current'


def test_changed_or_tampered_artifacts_invalidate_the_export(review, monkeypatch):
    client, runtime, repo, job_id, root = review
    monkeypatch.chdir(root)
    stage(client)
    folder = Path(snapshot(client)['export']['path'])
    (folder / 'final.mp4').write_bytes(b'tampered')
    assert verify(folder)['status'] == 'invalid'
    assert client.get('/api/batch-plans/one/export').json()['status'] == 'invalid'
    (folder / 'final.mp4').write_bytes(b'stub final bytes')
    assert client.get('/api/batch-plans/one/export').json()['status'] == 'current'
    (root / 'final').write_bytes(b'a different final render')        # the reviewed source changes
    item = snapshot(client)
    assert item['state'] == 'needs_review' and item['export']['status'] == 'stale'
    assert client.get('/api/batch-plans/one/export').json()['status'] == 'stale'


def test_a_failed_export_never_records_ready(review, monkeypatch):
    client, runtime, repo, job_id, root = review
    monkeypatch.chdir(root)
    (root / 'data').mkdir()
    (root / 'data' / 'batch-exports').write_text('a file where the export folder should be')
    csrf(client)
    identity = snapshot(client)['reviewed_identity']
    assert action(client, 'approve', identity).status_code == 200
    assert action(client, 'ready', identity).status_code == 409
    assert snapshot(client)['state'] == 'approved' and snapshot(client)['export'] is None
