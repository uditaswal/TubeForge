"""Reference contracts are data-only and do not fetch or approve content."""
from datetime import UTC, datetime, timedelta
import json
from pathlib import Path

from pydantic import ValidationError
import pytest

from tubeforge.domain.reference_video import (
    ReferenceIntakeRequest, ReferenceIntakeView, ReferenceSnapshot, canonical_reference_url,
)
from tubeforge.pipeline.long_form_reference import reference_cache_key, reference_content_identity

URL = 'https://www.youtube.com/watch?v=AbCdEfGhI_1'


def snapshot_data():
    return dict(extractor_version='fixture-v1', reference_url=URL, video_id='AbCdEfGhI_1',
        title='Synthetic explanation', creator='Fixture channel',duration_seconds=600,
        captured_at='2026-11-07T10:00:00Z', language='en',transcript_origin='captions',
        cues=[dict(start_seconds=0,end_seconds=10,text='Synthetic reference text only.')],
        limitations=['Caption-only extraction; video and audio were not inspected.'])


@pytest.mark.parametrize('url', [URL, 'https://youtu.be/AbCdEfGhI_1?t=20',
    'https://m.youtube.com/watch?v=AbCdEfGhI_1&list=example',
    'https://youtube.com/shorts/AbCdEfGhI_1', 'https://youtube.com/embed/AbCdEfGhI_1',
    'https://youtube.com/live/AbCdEfGhI_1', 'https://WWW.YOUTUBE.COM:443/watch?v=AbCdEfGhI_1&si=tracking'])
def test_canonical_video_links(url):
    assert canonical_reference_url(url) == URL


@pytest.mark.parametrize('url', ['http://youtu.be/AbCdEfGhI_1', 'https://youtube.com.evil.test/watch?v=AbCdEfGhI_1',
    'https://user:pass@youtube.com/watch?v=AbCdEfGhI_1', 'https://127.0.0.1/watch?v=AbCdEfGhI_1',
    'https://youtube.com:444/watch?v=AbCdEfGhI_1', 'https://youtube.com/playlist?list=example',
    'https://youtube.com/watch?v=AbCdEfGhI_1&v=', 'https://youtube.com/watch?v=bad',
    'https://youtube.com/watch?v=AbCdEfGhI_1\n', 'https://youtu.be/AbCdEfGhI_1/extra'])
def test_unsafe_or_ambiguous_reference_links_fail(url):
    with pytest.raises(ValueError): canonical_reference_url(url)


@pytest.mark.parametrize('field,value', [
    ('video_id','different01'), ('title',' '), ('captured_at','2026-11-07T10:00:00'),
    ('language',' '), ('duration_seconds',float('inf')), ('transcript_origin','unavailable'),
    ('cues',[]), ('cues',[dict(start_seconds=4,end_seconds=3,text='Backwards')]),
    ('cues',[dict(start_seconds=0,end_seconds=601,text='Outside')]),
    ('cues',[dict(start_seconds=0,end_seconds=1,text=' ')]),
    ('cues',[dict(start_seconds=float('nan'),end_seconds=1,text='Invalid')]),
    ('cues',[dict(start_seconds=0,end_seconds=float('inf'),text='Invalid')]),
    ('cues',[dict(start_seconds=-1,end_seconds=1,text='Invalid')]),
    ('cues',[dict(start_seconds=4,end_seconds=6,text='Later'), dict(start_seconds=1,end_seconds=3,text='Earlier')]),
])
def test_invalid_snapshot_evidence_fails(field,value):
    raw = snapshot_data(); raw[field]=value
    with pytest.raises(ValidationError): ReferenceSnapshot.model_validate(raw)


def test_unavailable_transcript_requires_limitations_but_preserves_metadata():
    raw = snapshot_data(); raw.update(transcript_origin='unavailable',cues=[])
    snapshot = ReferenceSnapshot.model_validate(raw)
    assert snapshot.title == raw['title']
    raw['limitations'] = []
    with pytest.raises(ValidationError): ReferenceSnapshot.model_validate(raw)


def test_caption_overlap_is_allowed_but_order_and_bytes_are_bounded():
    raw = snapshot_data(); raw['cues'] = [dict(start_seconds=0,end_seconds=5,text='first'),dict(start_seconds=2,end_seconds=6,text='overlap')]
    assert len(ReferenceSnapshot.model_validate(raw).cues) == 2
    raw['cues'] = [dict(start_seconds=i,end_seconds=i+1,text='界'*4000) for i in range(100)]
    with pytest.raises(ValidationError,match='byte budget'): ReferenceSnapshot.model_validate(raw)


def test_cache_identity_ignores_capture_time_only_and_preserves_original():
    snapshot = ReferenceSnapshot.model_validate(snapshot_data())
    request = ReferenceIntakeRequest(reference_url=URL,target_duration_seconds=600)
    recaptured = snapshot.model_copy(update={'captured_at': datetime.now(UTC)+timedelta(days=1)})
    assert reference_content_identity(snapshot) == reference_content_identity(recaptured)
    assert reference_cache_key(request,snapshot) == reference_cache_key(request,recaptured)
    for field,value in [('title','Changed title'),('extractor_version','fixture-v2'),('language','hi')]:
        assert reference_content_identity(snapshot.model_copy(update={field:value})) != reference_content_identity(snapshot)
    assert reference_cache_key(request.model_copy(update={'target_duration_seconds':900}),snapshot) != reference_cache_key(request,snapshot)
    assert snapshot.captured_at != recaptured.captured_at


def test_client_cannot_inject_server_identity_or_approval():
    for key,value in [('approved',True),('snapshot_sha256','0'*64),('fetch_succeeded',True)]:
        with pytest.raises(ValidationError):
            ReferenceIntakeRequest.model_validate(dict(reference_url=URL,target_duration_seconds=600,**{key:value}))


@pytest.mark.parametrize('state', ['pending','ready','needs_input','failed'])
def test_truthful_intake_projections(state):
    raw = dict(intake_id='fixture',revision=1,request=dict(reference_url=URL,target_duration_seconds=600),state=state)
    if state == 'ready': raw['snapshot']=snapshot_data()
    elif state != 'pending': raw.update(failure_code='captions_unavailable',message='Supply a timestamped transcript.')
    assert ReferenceIntakeView.model_validate(raw).state == state
    if state in {'pending','ready'}: raw.update(failure_code='retrieval_failed',message='Failed')
    else: raw['message']=None
    with pytest.raises(ValidationError): ReferenceIntakeView.model_validate(raw)


def test_ready_intake_cannot_claim_unavailable_or_wrong_language_transcript():
    raw = dict(intake_id='fixture',revision=1,request=dict(reference_url=URL,target_duration_seconds=600),state='ready',snapshot=snapshot_data())
    raw['snapshot']['language']='hi'
    with pytest.raises(ValidationError,match='language'): ReferenceIntakeView.model_validate(raw)
    raw['snapshot'].update(language='en',transcript_origin='unavailable',cues=[])
    with pytest.raises(ValidationError,match='usable'): ReferenceIntakeView.model_validate(raw)


def test_schema_snapshots_stay_in_sync():
    for model in [ReferenceSnapshot,ReferenceIntakeRequest,ReferenceIntakeView]:
        path=Path(__file__).parent/'fixtures/long_form'/f'{model.__name__}.schema.json'
        assert json.loads(path.read_text()) == model.model_json_schema()


def test_transcript_changes_invalidate_semantic_cache_identity():
    raw=snapshot_data()
    first=ReferenceSnapshot.model_validate(raw)
    raw['cues'][0]['text']='Changed explanation'
    assert reference_content_identity(ReferenceSnapshot.model_validate(raw)) != reference_content_identity(first)


def test_intake_supplied_transcript_is_bounded_and_does_not_grant_ready_state():
    request=ReferenceIntakeRequest(reference_url=URL,target_duration_seconds=600,supplied_cues=ReferenceSnapshot.model_validate(snapshot_data()).cues)
    assert request.supplied_cues[0].text
    with pytest.raises(ValidationError):
        ReferenceIntakeRequest(reference_url=URL,target_duration_seconds=600,supplied_cues=[dict(start_seconds=3,end_seconds=4,text='Later'),dict(start_seconds=1,end_seconds=2,text='Earlier')])
