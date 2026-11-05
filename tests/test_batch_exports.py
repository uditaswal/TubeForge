import hashlib
import json
import os
from pathlib import Path

import pytest
from sqlalchemy import select
from test_batch_review_api import review, snapshot, action, csrf
from tubeforge.db.models import ArtifactRecord, TopicRecord


def info(runtime):
    with runtime.database.session_factory() as session:
        return json.loads(session.get(TopicRecord, 'batch-one').options_json).get('batch_export')


def stage(client):
    identity = snapshot(client)['reviewed_identity']
    assert action(client, 'approve', identity).status_code == 200
    response = action(client, 'ready', identity)
    assert response.status_code == 200, response.text
    return identity


def test_atomic_export_contents_idempotency_and_authenticated_open(review):
    client, runtime, repo, job_id, root = review
    csrf(client)
    identity = stage(client)
    export = info(runtime)
    folder = Path(export['path'])
    assert folder.is_symlink()
    assert folder.parts[-3:] == ('default', '2026-11-01', 'one')
    manifest = json.loads((folder / 'package.json').read_text())
    for name, expected in manifest['files'].items():
        assert hashlib.sha256((folder / name).read_bytes()).hexdigest() == expected
    assert manifest['plan_id'] == 'default' and manifest['title'] == 'One'
    assert manifest['publish_at'] == '2026-11-01T10:00:00+05:30'
    assert manifest['qa']['exit_code'] == 0
    assert manifest['reviewed_identity'] == identity
    assert set(['description', 'tags', 'thumbnail_text', 'source_urls', 'reviewed_checksums']) <= manifest.keys()
    original_target, original_mtime = folder.resolve(), folder.lstat().st_mtime_ns
    assert action(client, 'ready', identity).status_code == 200
    assert folder.resolve() == original_target and folder.lstat().st_mtime_ns == original_mtime
    url = snapshot(client)['export_url']
    assert client.get(url).status_code == 200
    assert 'package.json' in client.get(url).text
    assert client.get(url + '/final.mp4').content == (root / 'final').read_bytes()
    assert client.get(url + '/../../not-allowed').status_code != 200
    client.cookies.clear()
    assert client.get(url).status_code == 401


def test_changed_artifact_invalidates_export_and_old_downloads(review):
    client, runtime, repo, job_id, root = review
    csrf(client)
    stage(client)
    export = info(runtime)
    url = snapshot(client)['export_url']
    (root / 'final').write_bytes(b'changed final')
    assert client.get(url + '/final.mp4').status_code == 409
    assert not Path(export['path']).is_symlink()
    assert snapshot(client)['state'] == 'needs_review'
    assert snapshot(client)['export_url'] is None


def test_reapproval_after_new_thumbnail_atomically_replaces_export(review):
    client, runtime, repo, job_id, root = review
    csrf(client)
    stage(client)
    old = info(runtime)
    (root / 'thumbnail').write_bytes(b'new registered thumbnail')
    with runtime.database.session_factory.begin() as session:
        artifact = session.scalar(select(ArtifactRecord).where(ArtifactRecord.job_id == job_id, ArtifactRecord.name == 'thumbnail'))
        artifact.checksum_sha256 = hashlib.sha256((root / 'thumbnail').read_bytes()).hexdigest()
    assert snapshot(client)['state'] == 'needs_review'
    stage(client)
    new = info(runtime)
    assert new['path'] == old['path']
    assert new['version'] != old['version']
    assert Path(new['path']).resolve() == Path(new['version'])
    assert (Path(new['path']) / 'thumbnail.jpg').read_bytes() == b'new registered thumbnail'
    assert (Path(old['version']) / 'thumbnail.jpg').read_bytes() == b'stub thumbnail'


def test_copy_failure_never_exposes_partial_export_or_marks_ready(review, monkeypatch):
    client, runtime, repo, job_id, root = review
    csrf(client)
    identity = snapshot(client)['reviewed_identity']
    action(client, 'approve', identity)
    def fail(*args, **kwargs):
        raise OSError('stub interrupted copy')
    monkeypatch.setattr('tubeforge.pipeline.publication_batch_export.shutil.copy2', fail)
    result = action(client, 'ready', identity)
    assert result.status_code == 409
    assert info(runtime) is None
    assert snapshot(client)['state'] == 'approved'
    assert snapshot(client)['export_url'] is None


def test_export_corruption_invalidates_ready_and_reject_removes_pointer(review):
    client, runtime, repo, job_id, root = review
    csrf(client)
    stage(client)
    export = info(runtime)
    (Path(export['path']) / 'final.mp4').write_bytes(b'staged corruption')
    assert snapshot(client)['export_url'] is None
    assert snapshot(client)['decision'] is None
    assert not Path(export['path']).is_symlink()


def test_pointer_promotion_failure_preserves_previous_complete_version(review, monkeypatch):
    from tubeforge.pipeline.publication_batch_export import BatchExportStore
    client, runtime, repo, job_id, root = review
    csrf(client)
    identity = stage(client)
    previous = info(runtime)
    pointer = Path(previous['path'])
    before = (pointer / 'package.json').read_bytes()
    current = snapshot(client)
    actual_replace = os.replace
    def interrupted(source, target):
        if Path(target) == pointer:
            raise OSError('stub pointer promotion failure')
        return actual_replace(source, target)
    monkeypatch.setattr('tubeforge.pipeline.publication_batch_export.os.replace', interrupted)
    store = BatchExportStore(root)
    with pytest.raises(OSError, match='promotion failure'):
        store.prepare(plan_id='default', short=current['short'], package=current['script'],
            disclosure=current['disclosure'], qa={**current['qa'], 'output': 'new checker detail'}, reviewed_identity=identity,
            reviewed_checksums=current['reviewed_checksums'], final=root / 'final', thumbnail=root / 'thumbnail',
            thumbnail_text='', script=root / 'content_package')
    assert pointer.resolve() == Path(previous['version'])
    assert (pointer / 'package.json').read_bytes() == before
    assert store.valid(previous, identity)


def test_script_changed_during_copy_rejects_staging(review, monkeypatch):
    import shutil
    client, runtime, repo, job_id, root = review
    csrf(client)
    identity = snapshot(client)['reviewed_identity']
    action(client, 'approve', identity)
    real_copy = shutil.copy2
    def changed(source, target):
        result = real_copy(source, target)
        (root / 'content_package').write_text('{"changed":"during export"}')
        return result
    monkeypatch.setattr('tubeforge.pipeline.publication_batch_export.shutil.copy2', changed)
    assert action(client, 'ready', identity).status_code == 409
    assert info(runtime) is None
    assert snapshot(client)['export_url'] is None


def test_ready_ui_shows_open_export_row_action(review):
    from test_batch_ui_runtime import runtime as javascript
    client, backend, repo, job_id, root = review
    context, run = javascript(client, client.get('/batch/review').text)
    run('list.children[0].children[0].onclick()')
    run('document.querySelector("#disclosureChoice").value="yes"')
    run('detail.querySelectorAll("#actions button")[0].onclick()')
    run('detail.querySelectorAll("#actions button")[3].onclick()')
    assert context.eval('list.children[0].children.some(x=>x.tagName==="a"&&x.textContent==="Open export")')
    url = context.eval('detail.children.find(x=>x.id==="exportLink").href')
    assert client.get(url).status_code == 200


def test_regeneration_clears_old_thumbnail_result_and_active_export(review):
    client, runtime, repo, job_id, root = review
    csrf(client)
    with runtime.database.session_factory.begin() as session:
        row = session.get(TopicRecord, 'batch-one')
        options = json.loads(row.options_json)
        options['batch_thumbnail'] = {'status':'available', 'text':'Old thumbnail'}
        row.options_json = json.dumps(options)
    identity = stage(client)
    previous = info(runtime)
    response = action(client, 'regenerate', identity)
    assert response.status_code == 200
    child = repo.for_job(response.json()['job_id'])
    assert 'batch_thumbnail' not in child
    assert 'batch_export' not in child
    assert not Path(previous['path']).is_symlink()


def test_disclosure_is_exported_and_changed_audio_requires_new_approval(review):
    client, runtime, repo, job_id, root = review
    csrf(client)
    identity = stage(client)
    manifest = json.loads((Path(info(runtime)['path']) / 'package.json').read_text())
    assert manifest['disclosure']['platform_disclosure_required'] is True
    assert manifest['disclosure']['job_id'] == job_id
    assert manifest['originality_report']['status'] == 'pass'
    audio = root / 'reference' / 'mix' / 'audio-provenance.json'
    audio.write_text(json.dumps({'audio_licenses': []}))
    assert snapshot(client)['reviewed_identity'] != identity
    assert snapshot(client)['export_url'] is None
    assert action(client, 'approve', snapshot(client)['reviewed_identity']).status_code == 409


def test_approval_requires_explicit_disclosure_choice(review):
    client, runtime, repo, job_id, root = review
    csrf(client)
    response = client.post('/api/batch-plans/one/review', json={'action': 'approve', 'reviewed_identity': snapshot(client)['reviewed_identity']})
    assert response.status_code == 409
    assert 'disclosure' in response.text
