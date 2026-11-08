from concurrent.futures import ThreadPoolExecutor
from datetime import UTC,datetime,timedelta
import json

import pytest
from sqlalchemy import select
from tubeforge.core.config import DatabaseConfig
from tubeforge.db.models import Base,LongFormStageCallRecord,LongFormWritingRecord
from tubeforge.db.session import create_database
from tubeforge.db.long_form_writing import LongFormWritingRepository,WritingConflict,WritingBudgetExhausted,sha
from tubeforge.domain.long_form_writing import LongFormHostRequest,LongFormTokenPolicy
from tubeforge.long_form.admission import measure
from test_long_form_writing import writing_inputs,review_result


@pytest.fixture
def store(tmp_path):
    database=create_database(DatabaseConfig(url=f'sqlite:///{tmp_path}/writing.db'));Base.metadata.create_all(database.engine)
    now=[datetime(2026,11,8,tzinfo=UTC)]
    repo=LongFormWritingRepository(database.session_factory,clock=lambda:now[0])
    yield database,repo,now
    database.dispose()


def create(repo,policy=None):
    message,draft,reference,packet=writing_inputs()
    run=repo.create(message.request,reference,intake_id='intake',intake_revision=1,actor='operator',token_policy=policy)
    return run,message,draft,reference,packet


def message_for(repo,claim,template,stage='research',draft=None,review=None):
    run=repo.get(claim['run_id']);raw=template.model_dump(mode='python')
    raw.update(operation='LongFormStageV1',stage=stage,brief_sha256=run['brief_sha256'],call_id=f"lf2-{run['id']}-call-{len(run['ledger']['calls'])+1}",
        source_packet_sha256=sha(json.dumps(run['source_packet'],ensure_ascii=False,sort_keys=True,separators=(',',':'))) if run['source_packet'] else None,
        token_policy=LongFormTokenPolicy.model_validate(run['token_policy']),draft=draft,review=review)
    return LongFormHostRequest.model_validate(raw)


def research_done(repo,claim,template,packet,usage=None):
    message=message_for(repo,claim,template);call=repo.reserve(claim,message,measure(message))
    repo.mark_transport(claim,call,'prepared');repo.mark_transport(claim,call,'dispatching')
    repo.finish_call(claim,call,{'output':{'status':'ready','assessment':'Synthetic research only.','sources':[{'source_id':s.source_id,'url':str(s.url),'title':s.title} for s in template.request.sources]},'provenance':{'web_searches':1}},succeeded=True,invocation_started=True,usage=usage if usage is not None else {'input_tokens':100,'output_tokens':20})
    repo.store_sources(claim,template.request,json.loads(packet))
    return call


def test_concurrent_creation_and_provider_change_reuse_one_immutable_budget(store):
    _,repo,_=store;template,_,reference,_=writing_inputs()
    def submit(owner):return repo.create(template.request.model_copy(update={'script_owner':owner}),reference,intake_id='intake',intake_revision=1,actor='operator')
    with ThreadPoolExecutor(max_workers=2) as pool:runs=list(pool.map(submit,['codex','claude']))
    assert runs[0]['id']==runs[1]['id'] and len(repo.list())==1
    captured=reference.model_copy(update={'captured_at':datetime(2026,11,9,tzinfo=UTC)})
    again=repo.create(template.request,captured,intake_id='intake',intake_revision=2,actor='operator',token_policy=LongFormTokenPolicy(total_reserved_tokens=250000))
    assert again['id']==runs[0]['id'] and again['token_policy']['total_reserved_tokens']==150000


def test_reservation_is_atomic_retained_and_unknown_usage_stays_unknown(store):
    _,repo,_=store;run,template,_,_,packet=create(repo);claim=repo.claim('worker')
    message=message_for(repo,claim,template)
    admission=measure(message)
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures=[pool.submit(repo.reserve,claim,message,admission) for _ in range(2)]
        results=[]
        for future in futures:
            try:results.append(future.result())
            except (WritingBudgetExhausted,WritingConflict):pass
    assert len(results)==1
    captured=repo.get(run['id']);assert captured['reserved_tokens']==admission['total_reservation']
    assert captured['usage']['input_tokens']['total'] is None
    call=results[0];repo.mark_transport(claim,call,'prepared');repo.mark_transport(claim,call,'dispatching')
    repo.finish_call(claim,call,{'output':{'status':'ready'}},succeeded=True,invocation_started=True,usage={'input_tokens':123})
    captured=repo.get(run['id']);assert captured['usage']['input_tokens']['total']==123
    assert captured['usage']['output_tokens']['total'] is None
    assert captured['reserved_tokens']==admission['total_reservation']
    with pytest.raises(WritingConflict,match='immutable'):repo.finish_call(claim,call,{'changed':True},succeeded=True,invocation_started=True)


def test_token_exhaustion_never_creates_a_call_and_cannot_widen_policy(store):
    _,repo,_=store;run,template,_,_,packet=create(repo,LongFormTokenPolicy(total_reserved_tokens=30000));claim=repo.claim('worker')
    research_done(repo,claim,template,packet)
    message=message_for(repo,claim,template,'draft')
    with pytest.raises(WritingBudgetExhausted):repo.reserve(claim,message,measure(message))
    assert len(repo.get(run['id'])['calls'])==1
    widened=message.model_copy(update={'token_policy':LongFormTokenPolicy()})
    with pytest.raises(WritingConflict):repo.reserve(claim,widened,measure(widened))


def test_expired_reclaimed_or_cancelled_worker_cannot_promote(store):
    _,repo,now=store;run,template,_,_,_=create(repo);old=repo.claim('old',lease_seconds=3)
    message=message_for(repo,old,template);call=repo.reserve(old,message,measure(message))
    assert repo.claim('other') is None
    now[0]+=timedelta(seconds=4);new=repo.claim('replacement')
    with pytest.raises(WritingConflict):repo.finish_call(old,call,{},succeeded=True,invocation_started=True)
    assert repo.stage_call(run['id'],'research')['call_id']==call
    repo.cancel(run['id'],'operator')
    with pytest.raises(WritingConflict):repo.mark_transport(new,call,'prepared')
    assert repo.claim('other') is None
    assert repo.get(run['id'])['reserved_tokens']>0


def test_source_capture_draft_decisions_and_stale_review_identity(store):
    _,repo,_=store;run,template,draft,_,packet=create(repo);claim=repo.claim('worker')
    research_done(repo,claim,template,packet)
    message=message_for(repo,claim,template,'draft');call=repo.reserve(claim,message,measure(message))
    repo.mark_transport(claim,call,'prepared');repo.mark_transport(claim,call,'dispatching')
    response={'output':draft.model_dump(mode='json')}
    repo.finish_call(claim,call,response,succeeded=True,invocation_started=True,usage={'input_tokens':100,'output_tokens':20})
    repo.store_draft(claim,draft);repo.release(claim,next_stage='review')
    claim=repo.claim('worker');message=message_for(repo,claim,template,'review',draft=draft)
    call=repo.reserve(claim,message,measure(message));review=review_result()
    repo.mark_transport(claim,call,'prepared');repo.mark_transport(claim,call,'dispatching')
    repo.finish_call(claim,call,{'output':review.model_dump(mode='json')},succeeded=True,invocation_started=True,usage={'input_tokens':100,'output_tokens':20})
    repo.store_review(claim,review);repo.release(claim,state='awaiting_review')
    current=repo.get(run['id']);assert current['review_applies_to_current_draft']
    with pytest.raises(WritingConflict):repo.decide(run['id'],'0'*64,'approved','operator')
    approved=repo.decide(run['id'],current['review_identity'],'approved','operator')
    assert approved['state']=='approved' and approved['decisions'][0]['draft_sha256']==current['draft_sha256']
    assert repo.claim('worker') is None
    assert len(approved['calls'])==3
    assert 'rendering is not enabled' in approved['message']


def test_payload_tampering_and_compact_history(store,monkeypatch):
    database,repo,_=store;run,template,_,_,_=create(repo);claim=repo.claim('worker')
    message=message_for(repo,claim,template);call=repo.reserve(claim,message,measure(message))
    assert len(json.dumps(repo.list()))<1000
    with database.session_factory() as db:
        row=db.get(LongFormStageCallRecord,call);row.payload_json+=' ';db.commit()
    with pytest.raises(ValueError,match='integrity'):repo.stage_call(run['id'],'research')


def test_observed_overrun_is_charged_and_never_refunded_or_hidden(store):
    _,repo,_=store;run,template,_,_,packet=create(repo);claim=repo.claim('worker')
    message=message_for(repo,claim,template);call=repo.reserve(claim,message,measure(message))
    repo.mark_transport(claim,call,'prepared');repo.mark_transport(claim,call,'dispatching')
    repo.finish_call(claim,call,{'output':{}},succeeded=True,invocation_started=True,usage={'input_tokens':10000,'output_tokens':145000,'reasoning_tokens':100})
    detail=repo.get(run['id'])
    assert detail['reserved_tokens']==155000
    assert detail['calls'][0]['charged_tokens']==155000
    assert detail['calls'][0]['reservation_tokens']<155000
    assert detail['usage']['reasoning_tokens']['total']==100


def test_unknown_essential_usage_blocks_further_reservation(store):
    _,repo,_=store;run,template,_,_,packet=create(repo);claim=repo.claim('worker')
    research_done(repo,claim,template,packet,usage={'input_tokens':100})
    candidate=message_for(repo,claim,template,'draft')
    with pytest.raises(WritingConflict,match='unknown launch/input/output usage'):
        repo.reserve(claim,candidate,measure(candidate))


def test_promoted_narration_must_equal_saved_invocation_output(store):
    _,repo,_=store;run,template,draft,_,packet=create(repo);claim=repo.claim('worker');research_done(repo,claim,template,packet)
    message=message_for(repo,claim,template,'draft');call=repo.reserve(claim,message,measure(message))
    repo.mark_transport(claim,call,'prepared');repo.mark_transport(claim,call,'dispatching')
    repo.finish_call(claim,call,{'output':draft.model_dump(mode='json')},succeeded=True,invocation_started=True,usage={'input_tokens':100,'output_tokens':100})
    repo.store_draft(claim,draft)
    changed=draft.model_copy(update={'package':draft.package.model_copy(update={'script_sections':(draft.package.script_sections[0].model_copy(update={'narration':draft.package.script_sections[0].narration+' Changed.'}),*draft.package.script_sections[1:])})})
    with pytest.raises(WritingConflict,match='immutable invocation'):repo.store_draft(claim,changed)
    assert repo.get(run['id'])['draft_sha256']==sha(draft.model_dump_json())


def test_reference_hash_cannot_accompany_fabricated_observation_text(store):
    _,repo,_=store;run,template,_,_,_=create(repo);claim=repo.claim('worker')
    message=message_for(repo,claim,template)
    altered=message.model_copy(update={'reference_excerpts':(message.reference_excerpts[0].model_copy(update={'text':'Fabricated source observation'}),)})
    with pytest.raises(WritingConflict,match='captured reference transcript'):repo.reserve(claim,altered,measure(altered))
    assert repo.get(run['id'])['calls']==[]
