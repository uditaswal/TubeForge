"""The selected disclosure comes from a current, checksum-bound Day review."""
from datetime import UTC, datetime
import hashlib
import json

import pytest

from test_batch_review_api import review, snapshot, csrf
from tubeforge.db.batch_review import BatchReviewRepository
from tubeforge.db.models import PublishingAssetRecord, SocialAccountRecord
from tubeforge.db.repositories import Artifact
from tubeforge.domain.states import JobState
from tubeforge.pipeline.manual_publish import ManualPublishService


def _setup(review, choice: bool, *, record: bool = True):
    client, runtime, _, job_id, root = review
    csrf(client)
    item = snapshot(client)
    if record:
        content = json.dumps(item["disclosure"], sort_keys=True).encode()
        path = root / "disclosure_record.json"
        path.write_bytes(content)
        runtime.artifacts.save(Artifact(job_id, JobState.FINAL_RENDERING, "disclosure_record", str(path), hashlib.sha256(content).hexdigest(), {}))
    response = client.post('/api/batch-plans/one/review', json={
        'action': 'approve', 'reviewed_identity': item['reviewed_identity'], 'disclosure_required': choice,
    })
    assert response.status_code == 200, response.text
    now = datetime.now(UTC)
    final_bytes = (root / 'final').read_bytes()
    digest = hashlib.sha256(final_bytes).hexdigest()
    stage = root / 'staging'
    stage.mkdir(exist_ok=True)
    (stage / f'{digest}.mp4').write_bytes(final_bytes)
    with runtime.database.session_factory.begin() as session:
        session.add(PublishingAssetRecord(id='asset-review', sha256=digest, staged_path=str(stage / f'{digest}.mp4'), source_job_id=job_id, size_bytes=len(final_bytes), duration_seconds=30, width=1080, height=1920, state='ready', created_at=now))
        session.add(SocialAccountRecord(id='yt-review', platform='youtube', display_name='Channel', external_account_id='UC-reviewed', auth_type='oauth', credential_ciphertext='encrypted', scopes_json='[]', token_expires_at=None, status='connected', capabilities_json='[]', is_default=False, disabled=False, last_validated_at=now, created_at=now, updated_at=now))
    repo = BatchReviewRepository(runtime.database.session_factory, root, runtime.orchestrator.music_catalog)
    service = ManualPublishService(runtime.database.session_factory, review_repository=repo)
    post = service.create_draft('asset-review', {'yt-review': {'title': 'Title', 'caption': 'Description'}})
    return service, post, root


@pytest.mark.parametrize('choice', [True, False])
def test_draft_binds_operator_disclosure_and_submits_current_review(review, choice):
    service, post, _ = _setup(review, choice)
    metadata = json.loads(service.deliveries(post.id)[0].metadata_json)
    assert metadata['contains_synthetic_media'] is choice
    assert metadata['disclosure_review']['contains_synthetic_media'] is choice
    assert service.submit(post.id, reviewed_identity=service.review_identity(post.id), actor='operator', supported_platforms={'youtube'}).state == 'queued'


def test_missing_or_changed_disclosure_refuses_submit(review):
    service, post, root = _setup(review, True)
    identity = service.review_identity(post.id)
    (root / 'disclosure_record.json').unlink()
    with pytest.raises(ValueError, match='disclosure'):
        service.submit(post.id, reviewed_identity=identity, actor='operator', supported_platforms={'youtube'})
    assert service.deliveries(post.id)[0].state == 'draft'



def test_review_to_private_upload_and_remote_verification_with_fake_transport(review, tmp_path):
    import subprocess
    import httpx
    from cryptography.fernet import Fernet
    from tubeforge.db.models import PublishJobRecord, TopicRecord
    from tubeforge.pipeline.delivery_executor import DeliveryExecutor
    from tubeforge.pipeline.delivery_queue import DeliveryQueue
    from tubeforge.providers.publishing.account_youtube import AccountYouTubeAdapter
    from tubeforge.security.secrets import TokenCipher

    _, runtime, _, job_id, root = review
    video = tmp_path / 'real-short.mp4'
    subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'color=s=90x160:d=1:r=5', '-f', 'lavfi', '-i', 'anullsrc=r=44100:cl=mono', '-t', '1', '-c:v', 'libx264', '-c:a', 'aac', '-y', str(video)], check=True, timeout=20)
    content = video.read_bytes()
    (root / 'final').write_bytes(content)
    digest = hashlib.sha256(content).hexdigest()
    runtime.artifacts.save(Artifact(job_id, JobState.FINAL_RENDERING, 'final', str(root / 'final'), digest, {}))
    with runtime.database.session_factory.begin() as session:
        topic = session.get(TopicRecord, 'batch-one')
        options = json.loads(topic.options_json)
        options['batch_qa']['artifact_checksum'] = digest
        topic.options_json = json.dumps(options)
    service, post, _ = _setup(review, True)
    service.submit(post.id, reviewed_identity=service.review_identity(post.id), actor='operator', supported_platforms={'youtube'})
    session_url = 'https://www.googleapis.com/upload/youtube/v3/videos?upload_id=fake'
    calls = []
    def respond(request):
        calls.append(request.method + ' ' + request.url.path)
        if request.url.path.endswith('/channels'):
            return httpx.Response(200, json={'items': [{'id': 'UC-reviewed'}]})
        if request.method == 'POST':
            assert json.loads(request.content)['status'] == {'privacyStatus': 'private', 'selfDeclaredMadeForKids': False, 'containsSyntheticMedia': True}
            return httpx.Response(200, headers={'Location': session_url})
        if request.method == 'PUT':
            assert request.content == content
            return httpx.Response(201, json={'id': 'remote-video'})
        return httpx.Response(200, json={'items': [{'id': 'remote-video', 'snippet': {'channelId': 'UC-reviewed', 'title': 'Title', 'description': 'Description'}, 'status': {'privacyStatus': 'private'}, 'processingDetails': {'processingStatus': 'succeeded'}}]})
    class Credentials:
        def resolve(self, account_id, owner):
            return {'token': 'fake'}
    client = httpx.Client(transport=httpx.MockTransport(respond))
    try:
        queue = DeliveryQueue(runtime.database.session_factory)
        executor = DeliveryExecutor(runtime.database.session_factory, queue, TokenCipher(Fernet.generate_key().decode()), root / 'staging', {'youtube': AccountYouTubeAdapter(client)}, Credentials())
        assert executor.run_once('worker')
        assert executor.run_once('worker')
        with runtime.database.session_factory() as session:
            assert session.get(PublishJobRecord, post.id).state == 'published'
        assert [entry.split()[0] for entry in calls] == ['GET', 'POST', 'PUT', 'GET']
    finally:
        client.close()
