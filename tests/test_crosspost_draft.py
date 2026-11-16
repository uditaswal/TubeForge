"""One current Day review prepares independent destination snapshots."""
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
import subprocess
from types import SimpleNamespace

from test_batch_review_api import review, snapshot, csrf
from test_publication_suggest import package
from tubeforge.db.batch_review import BatchReviewRepository
from tubeforge.db.models import PublishJobRecord, SocialAccountRecord, TopicRecord
from tubeforge.db.repositories import Artifact
from tubeforge.domain.states import JobState
from tubeforge.pipeline.delivery_queue import DeliveryQueue
from tubeforge.pipeline.manual_publish import ManualPublishService
from tubeforge.pipeline.publication_suggest import suggest


def _approved(review, tmp_path, monkeypatch):
    client, runtime, _, job_id, root = review
    csrf(client)
    video = root / 'final.mp4'
    subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'color=s=90x160:r=5:d=1', '-f', 'lavfi', '-i', 'anullsrc=r=44100:cl=mono', '-t', '1', '-c:v', 'libx264', '-c:a', 'aac', '-y', str(video)], check=True, timeout=20)
    digest = hashlib.sha256(video.read_bytes()).hexdigest()
    runtime.artifacts.save(Artifact(job_id, JobState.FINAL_RENDERING, 'final', str(video), digest, {}))
    with runtime.database.session_factory.begin() as session:
        topic = session.get(TopicRecord, 'batch-one')
        options = json.loads(topic.options_json)
        options['batch_qa']['artifact_checksum'] = digest
        topic.options_json = json.dumps(options)
    item = snapshot(client)
    record = json.dumps(item['disclosure'], sort_keys=True).encode()
    path = root / 'disclosure_record.json'
    path.write_bytes(record)
    runtime.artifacts.save(Artifact(job_id, JobState.FINAL_RENDERING, 'disclosure_record', str(path), hashlib.sha256(record).hexdigest(), {}))
    now = datetime.now(UTC)
    with runtime.database.session_factory.begin() as session:
        for account_id, platform, external in [('yt', 'youtube', 'UC-one'), ('ig', 'instagram', 'ig-one')]:
            session.add(SocialAccountRecord(id=account_id, platform=platform, display_name=account_id, external_account_id=external, auth_type='oauth', credential_ciphertext='fake', scopes_json='[]', token_expires_at=None, status='connected', capabilities_json='[]', is_default=False, disabled=False, last_validated_at=now, created_at=now, updated_at=now))
    # This synthetic review fixture uses a minimal content package; suggestion behavior
    # is independently exercised with the production-shaped checked-in fixture.
    monkeypatch.setattr('tubeforge.pipeline.publication_crosspost.ContentPackage', SimpleNamespace(model_validate=lambda value: package()))
    return client, runtime, item, digest


def test_approved_review_prepares_bound_crosspost_and_isolates_failure(review, tmp_path, monkeypatch):
    client, runtime, item, digest = _approved(review, tmp_path, monkeypatch)
    endpoint = '/api/batch-plans/one/prepare-post'
    payload = {'reviewed_identity': item['reviewed_identity'], 'destination_account_ids': ['yt', 'ig']}
    assert client.post(endpoint, json=payload).status_code == 409
    assert client.post('/api/batch-plans/one/review', json={'action': 'approve', 'reviewed_identity': item['reviewed_identity'], 'disclosure_required': True}).status_code == 200
    assert client.post(endpoint, json={**payload, 'reviewed_identity': '0' * 64}).status_code == 409
    preview = client.get('/api/batch-plans/one/post-defaults', params={'reviewed_identity': item['reviewed_identity']})
    assert preview.status_code == 200 and preview.json()['asset_sha256'] == digest
    assert preview.json()['youtube']['title'] == suggest(package())['title']
    assert preview.json()['instagram']['caption'] == suggest(package())['description']
    response = client.post(endpoint, json=payload)
    assert response.status_code == 201, response.text
    result = response.json()
    assert result['state'] == 'draft' and result['source_review_identity'] == item['reviewed_identity']
    by_platform = {entry['platform']: entry for entry in result['destinations']}
    expected = suggest(package())
    assert by_platform['youtube']['metadata']['title'] == expected['title']
    assert by_platform['youtube']['metadata']['caption'] == expected['description']
    assert by_platform['youtube']['metadata']['tags'] == expected['tags']
    assert by_platform['youtube']['metadata']['contains_synthetic_media'] is True
    caption = by_platform['instagram']['metadata']['caption']
    assert caption == expected['description'] and len(caption) <= 2200
    assert len(by_platform['instagram']['metadata']['hashtags']) <= 30
    assert len(by_platform['youtube']['metadata']['thumbnail_sha256']) == 64
    with runtime.database.session_factory() as session:
        post = session.get(PublishJobRecord, result['id'])
        assert json.loads(post.metadata_json)['source_review_identity'] == item['reviewed_identity']
    repo = BatchReviewRepository(runtime.database.session_factory, runtime.orchestrator.artifact_root, runtime.orchestrator.music_catalog)
    drafts = ManualPublishService(runtime.database.session_factory, review_repository=repo)
    import pytest
    with pytest.raises(ValueError, match='explicit confirmation'):
        drafts.submit(result['id'], reviewed_identity=result['reviewed_identity'], actor='operator', supported_platforms={'youtube', 'instagram'})
    assert all(row.state == 'draft' for row in drafts.deliveries(result['id']))
    drafts.submit(result['id'], reviewed_identity=result['reviewed_identity'], actor='operator', supported_platforms={'youtube', 'instagram'}, confirmed_public_accounts=frozenset({'ig'}))
    with runtime.database.session_factory() as session:
        audit = json.loads(session.get(PublishJobRecord, result['id']).metadata_json)['public_confirmation']
        assert audit['account_ids'] == ['ig'] and audit['actor'] == 'operator'
        assert audit['reviewed_identity'] == result['reviewed_identity']
    queue = DeliveryQueue(runtime.database.session_factory)
    youtube_claim = queue.claim_next('yt-worker', platforms={'youtube'})
    assert youtube_claim
    queue.preflight_failed(youtube_claim, 'simulated YouTube failure')
    instagram_claim = queue.claim_next('ig-worker', platforms={'instagram'})
    assert instagram_claim and instagram_claim.delivery_id == by_platform['instagram']['id']
    with runtime.database.session_factory() as session:
        assert session.get(PublishJobRecord, result['id']).state == 'partial_failure'
    assert client.post(endpoint, json=payload).status_code == 409


def test_instagram_defaults_limit_caption_and_inline_hashtags():
    import re
    from tubeforge.pipeline.publication_crosspost import instagram_caption
    caption, hashtags = instagram_caption('Intro ' + ' '.join(f'#topic{i}' for i in range(45)) + ' x' * 2500)
    assert len(caption) <= 2200
    assert len(re.findall(r'(?<!\w)#[\w]+', caption)) == 30
    assert len(hashtags) == 30


def test_instagram_failure_does_not_stop_youtube(review, tmp_path, monkeypatch):
    client, runtime, item, _ = _approved(review, tmp_path, monkeypatch)
    assert client.post('/api/batch-plans/one/review', json={'action': 'approve', 'reviewed_identity': item['reviewed_identity'], 'disclosure_required': False}).status_code == 200
    response = client.post('/api/batch-plans/one/prepare-post', json={'reviewed_identity': item['reviewed_identity'], 'destination_account_ids': ['yt', 'ig']})
    assert response.status_code == 201, response.text
    data = response.json()
    repo = BatchReviewRepository(runtime.database.session_factory, runtime.orchestrator.artifact_root, runtime.orchestrator.music_catalog)
    drafts = ManualPublishService(runtime.database.session_factory, review_repository=repo)
    drafts.submit(data['id'], reviewed_identity=data['reviewed_identity'], actor='operator', supported_platforms={'youtube', 'instagram'}, confirmed_public_accounts=frozenset({'ig'}))
    queue = DeliveryQueue(runtime.database.session_factory)
    instagram = queue.claim_next('ig-worker', platforms={'instagram'})
    assert instagram
    queue.preflight_failed(instagram, 'simulated Instagram failure')
    youtube = queue.claim_next('yt-worker', platforms={'youtube'})
    assert youtube and youtube.platform == 'youtube'
