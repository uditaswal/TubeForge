"""Atomic LF2 reservations and immutable invocation evidence in TubeForge SQLite."""
from __future__ import annotations

from datetime import UTC,datetime,timedelta
import hashlib
import json
from uuid import uuid4
from sqlalchemy import select,text,func,or_

from tubeforge.db.models import LongFormWritingRecord as Run,LongFormStageCallRecord as Call,LongFormWritingEventRecord as Event,LongFormWritingDecisionRecord as Decision
from tubeforge.domain.contracts import ContentRequest
from tubeforge.domain.reference_video import ReferenceSnapshot
from tubeforge.domain.long_form_budget import LongFormCallLedger,ObservedUsage
from tubeforge.domain.long_form_writing import LongFormHostRequest,LongFormTokenPolicy,LongFormDraftResult
from tubeforge.pipeline.long_form_budget import reserve_stage_call,finish_stage_call,summarize_usage
from tubeforge.pipeline.long_form_reference import reference_content_identity
from tubeforge.long_form.identity import writing_identity
from tubeforge.long_form.admission import measure
from tubeforge.long_form.wire import encode


class WritingConflict(ValueError):pass
class WritingBudgetExhausted(ValueError):pass


def sha(value):return hashlib.sha256(value.encode() if isinstance(value,str) else value).hexdigest()


def json_text(value):return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'))


class LongFormWritingRepository:
    def __init__(self,sessions,clock=None):self.sessions=sessions;self.clock=clock or (lambda:datetime.now(UTC))

    def _event(self,db,row,event,actor,**details):
        db.add(Event(run_id=row.id,event=event,actor=actor[:128],details_json=json_text(details),created_at=self.clock()))

    def create(self,request,reference,*,intake_id,intake_revision,actor,token_policy=None,research_required=True):
        policy=token_policy or LongFormTokenPolicy()
        if reference.transcript_origin=='unavailable' or reference.language.casefold()!=request.language.casefold():
            raise ValueError('Script preparation needs usable reference text in the requested language')
        if request.prompt_version!='m6-content-long-v1' or request.aspect_ratio!='16:9' or not 600<=request.target_duration_seconds<=900 or request.review_mode!='manual':
            raise ValueError('Preparation requires the explicit long-form profile and manual script review')
        key=writing_identity(request,reference)
        with self.sessions() as db:
            db.execute(text('BEGIN IMMEDIATE'))
            row=db.scalar(select(Run).where(Run.brief_sha256==key))
            if row is None:
                now=self.clock();identity=uuid4().hex;reference_json=reference.model_dump_json()
                row=Run(id=identity,brief_sha256=key,intake_id=intake_id,intake_revision=intake_revision,
                    initial_request_json=request.model_dump_json(),request_json=request.model_dump_json(),reference_json=reference_json,reference_sha256=sha(reference_json),
                    ledger_json=LongFormCallLedger(brief_sha256=key,research_required=research_required).model_dump_json(),token_policy_json=policy.model_dump_json(),reserved_tokens=0,
                    state='pending',next_stage='research' if research_required else 'capture_sources',created_at=now,updated_at=now)
                db.add(row);self._event(db,row,'preparation_created',actor)
            else:self._event(db,row,'duplicate_preparation_reused',actor)
            db.commit();return self.get(row.id)

    def _row(self,db,run_id):
        row=db.get(Run,run_id)
        if row is None:raise KeyError('Script preparation not found')
        return row

    def _owned(self,db,claim):
        row=self._row(db,claim['run_id'])
        if row.claim_token!=claim['token'] or row.state not in {'working','reconciling'} or not row.lease_expires_at or row.lease_expires_at.replace(tzinfo=UTC)<=self.clock():
            raise WritingConflict('Script preparation ownership expired or was revoked')
        return row

    def owns(self,claim):
        try:
            with self.sessions() as db:self._owned(db,claim)
            return True
        except (WritingConflict,KeyError):return False

    def _check_integrity(self,row):
        if sha(row.reference_json)!=row.reference_sha256:raise ValueError('Reference snapshot integrity failed')
        reference=ReferenceSnapshot.model_validate_json(row.reference_json)
        initial=ContentRequest.model_validate_json(row.initial_request_json)
        current=ContentRequest.model_validate_json(row.request_json)
        if initial.model_dump(exclude={'sources'})!=current.model_dump(exclude={'sources'}):raise ValueError('Canonical brief changed outside source capture')
        if writing_identity(initial,reference)!=row.brief_sha256:raise ValueError('Preparation brief integrity failed')
        if row.draft_json is not None and sha(row.draft_json)!=row.draft_sha256:raise ValueError('Script draft integrity failed')
        if row.draft_json is not None and LongFormDraftResult.model_validate_json(row.draft_json).package.request!=current:
            raise ValueError('Current draft differs from the canonical source packet')
        if row.source_packet_json:
            from tubeforge.pipeline.scene_contracts import validate_request_source_packet
            validate_request_source_packet(current,row.source_packet_json.encode())
        ledger=LongFormCallLedger.model_validate_json(row.ledger_json)
        if ledger.brief_sha256!=row.brief_sha256:raise ValueError('Budget brief integrity failed')
        return ledger

    def _call_view(self,call):
        return dict(call_id=call.id,stage=call.stage,state=call.state,ordinal=call.ordinal,provider=call.provider,model=call.model,
            admission=json.loads(call.admission_json),reservation_tokens=call.reservation_tokens,charged_tokens=call.charged_tokens,invocation_started=call.invocation_started,
            usage=json.loads(call.usage_json) if call.usage_json else None,response=json.loads(call.response_json) if call.response_json else None,
            failure_message=call.failure_message,created_at=call.created_at.replace(tzinfo=UTC).isoformat(),
            finished_at=call.finished_at.replace(tzinfo=UTC).isoformat() if call.finished_at else None)

    def _detail(self,db,row):
        ledger=self._check_integrity(row)
        calls=db.scalars(select(Call).where(Call.run_id==row.id).order_by(Call.ordinal)).all()
        if sum(c.charged_tokens for c in calls)!=row.reserved_tokens or len(calls)!=len(ledger.calls):
            raise ValueError('Durable call reservation history differs from ledger')
        policy=LongFormTokenPolicy.model_validate_json(row.token_policy_json)
        packet=json.loads(row.source_packet_json) if row.source_packet_json else None
        bundle=dict(draft_sha256=row.draft_sha256,reference_sha256=row.reference_sha256,
            source_packet_sha256=sha(row.source_packet_json) if row.source_packet_json else None,
            planning_sha256=sha(row.planning_json) if row.planning_json else None,score_report_sha256=sha(row.score_report_json) if row.score_report_json else None,
            review_sha256=sha(row.review_json) if row.review_json else None,reviewed_draft_sha256=row.reviewed_draft_sha256)
        decisions=db.scalars(select(Decision).where(Decision.run_id==row.id).order_by(Decision.created_at)).all()
        events=db.scalars(select(Event).where(Event.run_id==row.id).order_by(Event.id.desc()).limit(60)).all()
        # Editorial outcomes remain visible even after routine worker events roll
        # out of the recent activity feed. Each run has at most two draft calls.
        draft_events=db.scalars(select(Event).where(Event.run_id==row.id,
            Event.event.in_(['draft_captured','draft_rejected'])).order_by(Event.id)).all()
        outcomes={}
        for event in draft_events:
            details=json.loads(event.details_json)
            call_id=details.get('call_id')
            if event.event=='draft_rejected':
                outcomes[call_id]=dict(disposition='rejected',reason=details.get('reason'))
            else:
                outcomes[call_id]=dict(disposition='current' if call_id==row.draft_call_id else 'superseded',reason=None)
        return dict(id=row.id,state=row.state,next_stage=row.next_stage,message=row.message,brief_sha256=row.brief_sha256,
            intake_id=row.intake_id,intake_revision=row.intake_revision,request=json.loads(row.request_json),reference=json.loads(row.reference_json),
            source_packet=packet,reference_snapshot_sha256=row.reference_sha256,draft=json.loads(row.draft_json) if row.draft_json else None,
            draft_sha256=row.draft_sha256,review=json.loads(row.review_json) if row.review_json else None,
            planning=json.loads(row.planning_json) if row.planning_json else None,score_report=json.loads(row.score_report_json) if row.score_report_json else None,
            review_applies_to_current_draft=bool(row.reviewed_draft_sha256 and row.reviewed_draft_sha256==row.draft_sha256),
            review_identity=sha(json_text(bundle)) if row.draft_json else None,
            ledger=ledger.model_dump(mode='json'),usage=summarize_usage(ledger),token_policy=policy.model_dump(mode='json'),reserved_tokens=row.reserved_tokens,
            expected_model=row.expected_model,
            calls=[{**self._call_view(c),'draft_outcome':outcomes.get(c.id)} for c in calls],decisions=[dict(decision=d.decision,actor=d.actor,draft_sha256=d.draft_sha256,review_identity=d.review_identity,created_at=d.created_at.replace(tzinfo=UTC).isoformat()) for d in decisions],
            activity=[dict(event=e.event,actor=e.actor,details=json.loads(e.details_json),created_at=e.created_at.replace(tzinfo=UTC).isoformat()) for e in reversed(events)])

    def get(self,run_id):
        with self.sessions() as db:return self._detail(db,self._row(db,run_id))

    def list(self):
        with self.sessions() as db:
            rows=db.execute(select(Run.id,Run.state,Run.next_stage,Run.reserved_tokens,Run.updated_at,func.json_extract(Run.request_json,'$.topic')).order_by(Run.created_at.desc()).limit(50)).all()
            return [dict(id=i,state=s,next_stage=stage,reserved_tokens=t,updated_at=updated.replace(tzinfo=UTC).isoformat(),topic=topic) for i,s,stage,t,updated,topic in rows]

    def claim(self,owner,lease_seconds=1200):
        now=self.clock()
        with self.sessions() as db:
            db.execute(text('BEGIN IMMEDIATE'))
            rows=db.scalars(select(Run).where(Run.state.in_(['pending','working','reconciling'])).order_by(Run.created_at).limit(100)).all()
            for row in rows:
                if row.lease_expires_at and row.lease_expires_at.replace(tzinfo=UTC)>now:continue
                self._check_integrity(row)
                previous_state=row.state
                row.claim_owner=owner;row.claim_token=uuid4().hex;row.lease_expires_at=now+timedelta(seconds=lease_seconds);row.state='working';row.updated_at=now
                self._event(db,row,'preparation_claimed',owner);db.commit()
                return dict(run_id=row.id,token=row.claim_token,owner=owner,previous_state=previous_state)
            db.commit();return None

    def has_eligible(self):
        with self.sessions() as db:
            return db.scalar(select(Run.id).where(Run.state.in_(['pending','working','reconciling']),
                or_(Run.lease_expires_at.is_(None),Run.lease_expires_at<=self.clock())).limit(1)) is not None

    def release(self,claim,*,state='pending',message=None,next_stage=None,delay_seconds=0):
        if state not in {'pending','reconciling','blocked','exhausted','awaiting_review'}:raise ValueError('Invalid preparation worker state')
        with self.sessions() as db:
            db.execute(text('BEGIN IMMEDIATE'));row=self._owned(db,claim)
            row.state=state;row.message=message[:1000] if message else None
            if next_stage is not None:row.next_stage=next_stage
            row.updated_at=self.clock();row.claim_owner=None;row.claim_token=None
            row.lease_expires_at=self.clock()+timedelta(seconds=delay_seconds) if delay_seconds else None
            self._event(db,row,'preparation_'+state,claim.get('owner','worker'),next_stage=row.next_stage)
            db.commit()

    def reserve(self,claim,message,admission,*,model=None):
        actual=measure(message)
        if actual!=admission:raise ValueError('Admission evidence differs from exact stage input')
        payload=encode(message).decode()
        with self.sessions() as db:
            db.execute(text('BEGIN IMMEDIATE'));row=self._owned(db,claim);ledger=self._check_integrity(row)
            if message.stage!=row.next_stage or message.brief_sha256!=row.brief_sha256:
                raise WritingConflict('Stage does not match the current immutable preparation')
            if message.request!=ContentRequest.model_validate_json(row.request_json) or message.reference_snapshot_sha256!=row.reference_sha256 or message.reference_content_sha256!=reference_content_identity(ReferenceSnapshot.model_validate_json(row.reference_json)):
                raise WritingConflict('Stage input changed the current source/reference identity')
            reference=ReferenceSnapshot.model_validate_json(row.reference_json)
            for excerpt in message.reference_excerpts:
                if excerpt.cue_index>=len(reference.cues) or excerpt.start_seconds!=reference.cues[excerpt.cue_index].start_seconds or excerpt.text not in reference.cues[excerpt.cue_index].text:
                    raise WritingConflict('Stage observations differ from the captured reference transcript')
            if message.token_policy!=LongFormTokenPolicy.model_validate_json(row.token_policy_json):raise WritingConflict('A stage cannot change its reserved token policy')
            if message.stage in {'draft','repair'} and sum(c.stage in {'draft','repair'} for c in ledger.calls)>=message.token_policy.maximum_narration_attempts:
                raise WritingBudgetExhausted('Configured narration allowance exhausted; no invocation launched')
            if model is not None:
                if not isinstance(model,str) or not model.strip() or len(model)>100:raise ValueError('Host must report a bounded model identity')
                if row.expected_model is not None and row.expected_model!=model:raise WritingConflict('Host model changed after preparation began; explicit operator review required')
                if message.resolved_model!=model:raise WritingConflict('Resolved model must be bound into the reserved request')
                row.expected_model=model
            previous=db.scalar(select(Call).where(Call.run_id==row.id).order_by(Call.ordinal).limit(1))
            if previous and json.loads(previous.admission_json)['resource_hashes']!=admission['resource_hashes']:
                raise WritingConflict('Skill resources changed after preparation began; no extra invocation launched')
            completed=db.scalars(select(Call).where(Call.run_id==row.id,Call.state.in_(['succeeded','failed']))).all()
            for call in completed:
                observed=ObservedUsage.model_validate_json(call.usage_json) if call.usage_json else None
                if call.invocation_started is None or (call.invocation_started and (observed is None or observed.input_tokens is None or observed.output_tokens is None)):
                    raise WritingConflict('Reconcile unknown launch/input/output usage before another invocation')
            if message.stage in {'review','repair'} and message.draft is not None:
                if message.draft.model_dump_json()!=row.draft_json:raise WritingConflict('Stage draft is no longer the exact current artifact')
                if message.stage=='repair' and (message.review is None or message.review.model_dump_json()!=row.review_json):raise WritingConflict('Repair findings differ from the recorded independent review')
            if message.stage=='repair' and message.rejected_output is not None:
                rejected=db.scalar(select(Call).where(Call.run_id==row.id,Call.stage=='draft',Call.response_json.is_not(None)))
                response=json.loads(rejected.response_json) if rejected else {}
                response=response.get('result',response)
                original=response.get('raw_output') if isinstance(response.get('raw_output'),str) else response.get('output')
                original=original if isinstance(original,str) else json_text(original)
                if message.rejected_output!=original or message.local_rejection!=(row.message,):raise WritingConflict('Raw repair input differs from the recorded rejected output/reason')
            expected_source=sha(row.source_packet_json) if row.source_packet_json else None
            if not ledger.research_required and message.stage=='draft' and expected_source is None:
                raise WritingConflict('Capture the supplied primary pages before reserving a draft')
            if message.source_packet_sha256!=expected_source:raise WritingConflict('Stage source packet identity changed')
            ordinal=len(ledger.calls)+1;expected=f'lf2-{row.id}-call-{ordinal}'
            if message.call_id!=expected:raise WritingConflict('Call ID must preserve the durable reservation order')
            if row.reserved_tokens+admission['total_reservation']>message.token_policy.total_reserved_tokens:
                raise WritingBudgetExhausted('Reserved text-token budget exhausted; no call was launched')
            try:updated=reserve_stage_call(ledger,message.stage,brief_sha256=row.brief_sha256)
            except ValueError as error:raise WritingBudgetExhausted(str(error)) from error
            db.add(Call(id=expected,run_id=row.id,ordinal=ordinal,stage=message.stage,state='reserved',payload_json=payload,payload_sha256=sha(payload),
                admission_json=json_text(admission),reservation_tokens=admission['total_reservation'],charged_tokens=admission['total_reservation'],provider=message.request.script_owner,model=model,created_at=self.clock()))
            row.ledger_json=updated.model_dump_json();row.reserved_tokens+=admission['total_reservation'];row.updated_at=self.clock()
            self._event(db,row,'stage_reserved',row.claim_owner,call_id=expected,stage=message.stage,reserved_tokens=admission['total_reservation'])
            db.commit();return expected

    def stage_call(self,run_id,stage):
        with self.sessions() as db:
            call=db.scalar(select(Call).where(Call.run_id==run_id,Call.stage==stage))
            if call is None:return None
            if sha(call.payload_json)!=call.payload_sha256:raise ValueError('Reserved call payload integrity failed')
            return dict(**self._call_view(call),message=LongFormHostRequest.model_validate_json(call.payload_json))

    def mark_transport(self,claim,call_id,state):
        if state not in {'prepared','dispatching','unknown'}:raise ValueError('Invalid transport checkpoint')
        with self.sessions() as db:
            db.execute(text('BEGIN IMMEDIATE'));row=self._owned(db,claim);call=db.get(Call,call_id)
            if call is None or call.run_id!=row.id or call.state in {'succeeded','failed'}:raise WritingConflict('Only the current unresolved call can advance')
            allowed={'prepared':{'reserved','prepared'},'dispatching':{'prepared'},'unknown':{'prepared','dispatching','unknown'}}
            if call.state not in allowed[state]:raise WritingConflict('Invalid transport transition')
            call.state=state;self._event(db,row,'stage_'+state,row.claim_owner,call_id=call_id);db.commit()

    def finish_call(self,claim,call_id,response,*,succeeded,invocation_started,usage=None,error=None):
        encoded=json_text(response)
        if len(encoded.encode())>2_000_000:raise ValueError('Stage response exceeds persistence bounds')
        usage=ObservedUsage.model_validate(usage) if usage is not None else None
        with self.sessions() as db:
            db.execute(text('BEGIN IMMEDIATE'));row=self._owned(db,claim);call=db.get(Call,call_id)
            if call is None or call.run_id!=row.id:raise WritingConflict('Call belongs to another preparation')
            if call.state in {'succeeded','failed'}:
                if call.response_json!=encoded:raise WritingConflict('Completed call evidence is immutable')
                return False
            if invocation_started is True and call.state not in {'dispatching','unknown'}:
                raise WritingConflict('Launched calls require a durable dispatch checkpoint')
            ledger=self._check_integrity(row)
            updated=finish_stage_call(ledger,f'call-{call.ordinal}',succeeded=succeeded,invocation_started=invocation_started,usage=usage)
            call.response_json=encoded;call.state='succeeded' if succeeded else 'failed';call.invocation_started=invocation_started
            call.usage_json=usage.model_dump_json() if usage else None;call.failure_message=error[:1000] if error else None;call.finished_at=self.clock()
            if usage and usage.input_tokens is not None and usage.output_tokens is not None:
                # Reasoning/cached counters may be subsets, so never add them
                # again. Preserve full reservation when usage is incomplete.
                charged=max(call.reservation_tokens,usage.input_tokens+usage.output_tokens)
                row.reserved_tokens+=charged-call.charged_tokens;call.charged_tokens=charged
            row.ledger_json=updated.model_dump_json();row.updated_at=self.clock()
            self._event(db,row,'stage_'+call.state,row.claim_owner,call_id=call.id,invocation_started=invocation_started)
            db.commit();return True

    def store_sources(self,claim,request,packet):
        from tubeforge.pipeline.scene_contracts import validate_request_source_packet
        encoded=json_text(packet);validate_request_source_packet(request,encoded.encode())
        with self.sessions() as db:
            db.execute(text('BEGIN IMMEDIATE'));row=self._owned(db,claim)
            initial=ContentRequest.model_validate_json(row.initial_request_json)
            ledger=LongFormCallLedger.model_validate_json(row.ledger_json)
            if ledger.research_required:
                call=db.scalar(select(Call).where(Call.run_id==row.id,Call.stage=='research'))
                if call is None or call.state!='succeeded':raise WritingConflict('Primary-source capture requires finished research')
                from tubeforge.providers.content.research import ResearchResult
                response=json.loads(call.response_json);result=response.get('result',response)
                research=ResearchResult.model_validate(result.get('output'))
                if research.status!='ready' or result.get('provenance',{}).get('web_searches',0)<1:
                    raise WritingConflict('Primary-source capture requires a completed research result with actual search evidence')
                known={(s.source_id,s.url) for s in research.sources}
            else:
                if ledger.calls or packet.get('retrieval_mode')!='lf2_operator_primary_capture':
                    raise WritingConflict('Supplied primary pages must be captured before model calls')
                known={(s.source_id,str(s.url)) for s in initial.sources}
            if len(request.sources)<2 or any((s.source_id,str(s.url)) not in known for s in request.sources):
                raise WritingConflict('Captured sources differ from the immutable source leads')
            if row.source_packet_json is not None:
                if row.source_packet_json!=encoded or row.request_json!=request.model_dump_json():raise WritingConflict('Captured source packet is immutable')
                return
            if request.model_dump(exclude={'sources'})!=initial.model_dump(exclude={'sources'}):raise WritingConflict('Research cannot rewrite the canonical brief')
            row.source_packet_json=encoded;row.request_json=request.model_dump_json();row.next_stage='draft';row.updated_at=self.clock()
            self._event(db,row,'primary_sources_captured',row.claim_owner,source_packet_sha256=sha(encoded));db.commit()

    def store_draft(self,claim,draft):
        if draft.package is None:raise ValueError('Cannot promote missing narration')
        encoded=draft.model_dump_json()
        with self.sessions() as db:
            db.execute(text('BEGIN IMMEDIATE'));row=self._owned(db,claim)
            call=db.scalar(select(Call).where(Call.run_id==row.id,Call.stage==row.next_stage))
            if row.next_stage not in {'draft','repair'} or call is None or call.state!='succeeded':raise WritingConflict('Draft must belong to the finished current narration call')
            if draft.package.request!=ContentRequest.model_validate_json(row.request_json):raise WritingConflict('Draft changed the trusted packet')
            from tubeforge.long_form.prompts import bind_draft
            from tubeforge.long_form.validation import validate_draft
            response=json.loads(call.response_json);result=response.get('result',response)
            normalized=bind_draft(result.get('output'),ContentRequest.model_validate_json(row.request_json))
            if normalized.model_dump_json()!=encoded:raise WritingConflict('Draft differs from the immutable invocation result')
            plan,scores=validate_draft(normalized,LongFormHostRequest.model_validate_json(call.payload_json),ReferenceSnapshot.model_validate_json(row.reference_json),source_packet_bytes=row.source_packet_json.encode())
            if row.draft_call_id==call.id:
                if row.draft_json!=encoded:raise WritingConflict('Promoted narration cannot change without another charged attempt')
                return False
            row.draft_json=encoded;row.draft_sha256=sha(encoded);row.draft_call_id=call.id;row.planning_json=plan.model_dump_json();row.score_report_json=json_text(scores);row.updated_at=self.clock()
            self._event(db,row,'draft_captured',row.claim_owner,call_id=call.id,draft_sha256=row.draft_sha256);db.commit()

    def store_review(self,claim,review):
        with self.sessions() as db:
            db.execute(text('BEGIN IMMEDIATE'));row=self._owned(db,claim)
            call=db.scalar(select(Call).where(Call.run_id==row.id,Call.stage=='review'))
            if row.next_stage!='review' or call is None or call.state!='succeeded' or row.draft_json is None:raise WritingConflict('Review must belong to the finished current review call')
            from tubeforge.domain.long_form_writing import LongFormReviewResult
            from tubeforge.long_form.validation import validate_review
            response=json.loads(call.response_json);result=response.get('result',response)
            normalized=LongFormReviewResult.model_validate(result.get('output'))
            message=LongFormHostRequest.model_validate_json(call.payload_json)
            if message.draft.model_dump_json()!=row.draft_json or normalized!=review:raise WritingConflict('Review differs from the exact recorded draft/result')
            validate_review(normalized,message.draft)
            if row.review_json is not None and row.review_json!=review.model_dump_json():raise WritingConflict('Independent review evidence is immutable')
            row.review_json=review.model_dump_json();row.reviewed_draft_sha256=row.draft_sha256;row.updated_at=self.clock()
            self._event(db,row,'review_captured',row.claim_owner,decision=review.decision,draft_sha256=row.draft_sha256);db.commit()

    def cancel(self,run_id,actor):
        with self.sessions() as db:
            db.execute(text('BEGIN IMMEDIATE'));row=self._row(db,run_id)
            if row.state in {'approved','rejected','cancelled'}:raise WritingConflict('This preparation already has a final decision')
            row.state='cancelled';row.message='Preparation cancelled. Reserved calls and any provider usage remain recorded.'
            row.claim_owner=None;row.claim_token=None;row.lease_expires_at=None;row.updated_at=self.clock()
            self._event(db,row,'preparation_cancelled',actor);db.commit()
        return self.get(run_id)

    def audit(self,claim,event,details):
        if len(json_text(details).encode())>2_000_000:raise ValueError('Audit evidence exceeds persistence bounds')
        with self.sessions() as db:
            db.execute(text('BEGIN IMMEDIATE'));row=self._owned(db,claim)
            self._event(db,row,event,row.claim_owner,**details);db.commit()

    def decide(self,run_id,review_identity,decision,actor):
        if decision not in {'approved','rejected'}:raise ValueError('Use an explicit script approval/rejection')
        with self.sessions() as db:
            db.execute(text('BEGIN IMMEDIATE'));row=self._row(db,run_id);detail=self._detail(db,row)
            if row.state!='awaiting_review' or not row.draft_sha256 or review_identity!=detail['review_identity']:
                raise WritingConflict('Review the exact current script and source/reference bundle before deciding')
            if any(c['state']=='pending' for c in detail['ledger']['calls']) or row.review_json is None:
                raise WritingConflict('Resolve the pending invocation and independent review before deciding')
            db.add(Decision(id=uuid4().hex,run_id=row.id,draft_sha256=row.draft_sha256,review_identity=review_identity,decision=decision,actor=actor[:128],created_at=self.clock()))
            row.state=decision;row.message='Exact script decision saved. Long-form rendering is not enabled by this workflow.';row.updated_at=self.clock()
            self._event(db,row,'script_'+decision,actor,review_identity=review_identity,draft_sha256=row.draft_sha256)
            db.commit()
        return self.get(run_id)
