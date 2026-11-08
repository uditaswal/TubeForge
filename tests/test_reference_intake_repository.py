from datetime import UTC,datetime,timedelta
from concurrent.futures import ThreadPoolExecutor
import json

import pytest
from sqlalchemy import select

from tubeforge.core.config import DatabaseConfig
from tubeforge.db.models import Base,ReferenceIntakeRecord
from tubeforge.db.session import create_database
from tubeforge.db.reference_intake import ReferenceIntakeRepository,IntakeConflict
from tubeforge.reference.service import ReferenceIntakeService,parse_supplied_transcript
from tubeforge.reference.extractor import YoutubeReferenceExtractor,IntakeFailure
from test_reference_intake_extractor import request,player,FixtureHTTP


@pytest.fixture
def store(tmp_path):
    db=create_database(DatabaseConfig(url=f'sqlite:///{tmp_path}/intake.db'));Base.metadata.create_all(db.engine)
    now=[datetime(2026,11,8,tzinfo=UTC)]
    repository=ReferenceIntakeRepository(db.session_factory,clock=lambda:now[0])
    yield db,repository,now
    db.dispose()


def service(repo,raw=None):return ReferenceIntakeService(repo,YoutubeReferenceExtractor(FixtureHTTP(raw)))


def test_atomic_duplicates_cache_and_immutable_refresh_history(store):
    db,repo,now=store
    with ThreadPoolExecutor(max_workers=2) as pool:values=list(pool.map(lambda _:repo.create(request(),'operator'),range(2)))
    assert len({v['intake']['intake_id'] for v in values})==1
    intake=values[0]['intake'];worker=service(repo)
    ready=worker.run_once('worker-one');assert ready['intake']['state']=='ready'
    original=ready['intake']['reference_snapshot_sha256']
    duplicate=repo.create(request(),'operator');assert duplicate['intake']['reference_snapshot_sha256']==original
    other=repo.create(request(language='en',channel_identity='other'),'operator')
    cached=worker.run_once('worker-two');assert cached['cache_hit'] is True
    assert len(worker.extractor.http.calls)==2
    fresh=repo.revise(intake['intake_id'],1,'operator',refresh=True)
    assert fresh['intake']['revision']==2
    worker.run_once('worker-two')
    assert len(worker.extractor.http.calls)==4
    assert repo.get(intake['intake_id'],1)['intake']['reference_snapshot_sha256']==original
    assert repo.get(intake['intake_id'])['intake']['revision']==2


def test_transcript_revision_reuses_saved_metadata_without_network(store):
    db,repo,now=store;raw=player();raw['captions']={};worker=service(repo,raw)
    first=repo.create(request(),'operator')['intake'];worker.run_once('worker')
    assert repo.get(first['intake_id'])['intake']['state']=='needs_input'
    cues=parse_supplied_transcript('1\n00:00:00,000 --> 00:00:03,000\nSupplied transcript.\n')
    revised=repo.revise(first['intake_id'],1,'operator',supplied_cues=cues)
    assert revised['intake']['revision']==2
    ready=worker.run_once('worker')
    assert ready['intake']['state']=='ready'
    assert ready['intake']['snapshot']['transcript_origin']=='supplied'
    assert len(worker.extractor.http.calls)==1
    assert repo.get(first['intake_id'],1)['intake']['state']=='needs_input'


def test_old_owner_cannot_promote_after_expiry_reclaim_or_cancel(store):
    db,repo,now=store;value=repo.create(request(),'operator')['intake']
    old=repo.claim('old',lease_seconds=5);assert repo.claim('other') is None
    snapshot=YoutubeReferenceExtractor(FixtureHTTP()).capture(request())
    now[0]+=timedelta(seconds=6);new=repo.claim('new')
    assert new['token']!=old['token']
    assert repo.finish(old,snapshot=snapshot) is False
    repo.cancel(value['intake_id'],1,'operator')
    assert repo.finish(new,snapshot=snapshot) is False
    assert repo.get(value['intake_id'])['intake']['failure_code']=='cancelled'


def test_stale_revisions_and_pending_revisions_are_conflicts(store):
    db,repo,now=store;value=repo.create(request(),'operator')['intake']
    with pytest.raises(IntakeConflict):repo.revise(value['intake_id'],1,'operator',refresh=True)
    service(repo).run_once('worker')
    repo.revise(value['intake_id'],1,'operator',refresh=True)
    with pytest.raises(IntakeConflict):repo.revise(value['intake_id'],1,'operator',refresh=True)


def test_snapshot_tampering_is_detected_and_claims_share_capture_lock(store):
    db,repo,now=store
    one=repo.create(request(),'operator')['intake'];repo.create(request(channel_identity='second'),'operator')
    claim=repo.claim('one');assert repo.claim('two') is None
    snapshot=YoutubeReferenceExtractor(FixtureHTTP()).capture(request())
    assert repo.finish(claim,snapshot=snapshot)
    with db.session_factory() as session:
        row=session.scalar(select(ReferenceIntakeRecord).where(ReferenceIntakeRecord.intake_id==one['intake_id']))
        row.snapshot_json+=' ';session.commit()
    with pytest.raises(ValueError,match='integrity'):repo.get(one['intake_id'])


def test_failed_capture_is_durable_retry_creates_new_revision(store):
    db,repo,now=store;value=repo.create(request(),'operator')['intake']
    class Failing:
        def capture(self,*args,**kwargs):raise IntakeFailure('retrieval_failed','Public capture timed out.')
    worker=ReferenceIntakeService(repo,Failing());failed=worker.run_once('worker')
    assert failed['intake']['state']=='failed'
    new=repo.revise(value['intake_id'],1,'operator',refresh=True)
    assert new['intake']['revision']==2
    assert repo.get(value['intake_id'],1)['intake']['message']=='Public capture timed out.'


def test_fresh_revision_after_supplied_transcript_fetches_source_again(store):
    _,repo,_=store;worker=service(repo)
    cues=parse_supplied_transcript('1\n00:00:00,000 --> 00:00:03,000\nSupplied text.\n')
    first=repo.create(request(supplied_cues=cues),'operator')['intake']
    supplied=worker.run_once('worker')['intake']
    fresh=repo.revise(first['intake_id'],1,'operator',refresh=True)
    assert fresh['intake']['request']['supplied_cues']==[]
    captured=worker.run_once('worker')['intake']
    assert captured['snapshot']['transcript_origin']=='captions'
    assert len(worker.extractor.http.calls)==3
    assert repo.get(first['intake_id'],1)['intake']['reference_snapshot_sha256']==supplied['reference_snapshot_sha256']


def test_history_is_compact_without_loading_full_detail(store,monkeypatch):
    _,repo,_=store;value=repo.create(request(),'operator')['intake']
    service(repo).run_once('worker')
    def forbidden(*args,**kwargs):raise AssertionError('History must not load full detail')
    monkeypatch.setattr(repo,'_detail',forbidden)
    rows=repo.list()
    assert rows[0]['intake']['intake_id']==value['intake_id']
    assert rows[0]['intake']['snapshot']=={'title':'Synthetic reference'}
    assert len(json.dumps(rows))<1000
    assert 'cues' not in json.dumps(rows) and 'supplied_cues' not in json.dumps(rows)


def test_worker_shutdown_leaves_pending_claim_for_restart(store):
    _,repo,now=store;value=repo.create(request(),'operator')['intake'];stopped=[False]
    class StoppingExtractor:
        def capture(self,*args,**kwargs):
            stopped[0]=True
            raise IntakeFailure('cancelled','Worker is stopping')
    assert ReferenceIntakeService(repo,StoppingExtractor()).run_once('stopping',cancelled=lambda:stopped[0]) is None
    assert repo.get(value['intake_id'])['intake']['state']=='pending'
    assert repo.claim('replacement') is None
    now[0]+=timedelta(seconds=121)
    assert service(repo).run_once('replacement')['intake']['state']=='ready'
