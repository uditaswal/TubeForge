"""Reference history/cache in the existing SQLite DB, with atomic claims."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
import hashlib
import json
from uuid import uuid4

from sqlalchemy import select, text, func, or_, and_

from tubeforge.db.models import ReferenceIntakeRecord as Row, ReferenceIntakeEventRecord as Event
from tubeforge.domain.reference_video import ReferenceIntakeRequest, ReferenceIntakeView, ReferenceSnapshot
from tubeforge.reference.extractor import EXTRACTOR_VERSION
from tubeforge.reference.brief import build_reference_brief


class IntakeConflict(ValueError): pass


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()


class ReferenceIntakeRepository:
    def __init__(self,session_factory,clock=None):
        self.sessions=session_factory;self.clock=clock or (lambda:datetime.now(UTC))

    def _event(self,db,row,event,actor,**details):
        db.add(Event(intake_id=row.intake_id,revision=row.revision,event=event,actor=actor[:128],
                     details_json=json.dumps(details),created_at=self.clock()))

    def _new(self,request,intake_id,revision,force_refresh=False):
        raw=request.model_dump(mode='json')
        return Row(row_id=uuid4().hex,intake_id=intake_id,revision=revision,request_key=digest(raw),
                   capture_key=digest(dict(url=request.reference_url,language=request.language,cues=raw['supplied_cues'],extractor=EXTRACTOR_VERSION)),
                   request_json=request.model_dump_json(),state='pending',force_refresh=force_refresh,cache_hit=False,created_at=self.clock())

    def create(self,request,actor):
        with self.sessions() as db:
            db.execute(text('BEGIN IMMEDIATE'))
            row=db.scalar(select(Row).where(Row.request_key==digest(request.model_dump(mode='json'))).order_by(Row.created_at.desc(),Row.revision.desc()).limit(1))
            if row is None:
                row=self._new(request,uuid4().hex,1);db.add(row)
                self._event(db,row,'intake_created',actor)
            else:self._event(db,row,'duplicate_reused',actor)
            db.commit();return self.get(row.intake_id,row.revision)

    def _row(self,db,intake_id,revision=None):
        query=select(Row).where(Row.intake_id==intake_id)
        if revision is not None:query=query.where(Row.revision==revision)
        row=db.scalar(query.order_by(Row.revision.desc()).limit(1))
        if row is None:raise KeyError('Reference intake not found')
        return row

    def _view(self,row):
        snapshot=None
        if row.snapshot_json is not None:
            if hashlib.sha256(row.snapshot_json.encode()).hexdigest()!=row.snapshot_sha256:
                raise ValueError('Saved reference snapshot integrity failed')
            snapshot=ReferenceSnapshot.model_validate_json(row.snapshot_json)
        return ReferenceIntakeView(intake_id=row.intake_id,revision=row.revision,
            request=ReferenceIntakeRequest.model_validate_json(row.request_json),state=row.state,snapshot=snapshot,
            failure_code=row.failure_code,message=row.message)

    @staticmethod
    def _stamp(value):
        return value.replace(tzinfo=UTC).isoformat() if value is not None else None

    def _detail(self,db,row):
        latest=db.scalar(select(Row.revision).where(Row.intake_id==row.intake_id).order_by(Row.revision.desc()).limit(1))
        events=db.scalars(select(Event).where(Event.intake_id==row.intake_id,Event.revision==row.revision).order_by(Event.id.desc()).limit(50)).all()
        revisions=db.execute(select(Row.revision,Row.state).where(Row.intake_id==row.intake_id).order_by(Row.revision.desc())).all()
        view=self._view(row)
        return dict(intake=view.model_dump(mode='json'),
                    observation_brief=build_reference_brief(view.snapshot,view.request.target_duration_seconds) if view.snapshot else None,
                    created_at=self._stamp(row.created_at),
                    finished_at=self._stamp(row.finished_at),cache_hit=row.cache_hit,is_latest=row.revision==latest,
                    revisions=[dict(revision=r,state=s) for r,s in revisions],
                    activity=[dict(event=e.event,actor=e.actor,created_at=self._stamp(e.created_at),details=json.loads(e.details_json)) for e in reversed(events)])

    def get(self,intake_id,revision=None):
        with self.sessions() as db:return self._detail(db,self._row(db,intake_id,revision))

    def list(self):
        with self.sessions() as db:
            # History polling must not transfer or deserialize every transcript.
            # Only the selected detail/export carries the full immutable context.
            latest=select(Row.intake_id,func.max(Row.revision).label('revision')).group_by(Row.intake_id).subquery()
            rows=db.execute(select(Row.intake_id,Row.revision,Row.state,Row.created_at,
                func.json_extract(Row.request_json,'$.reference_url'),
                func.json_extract(Row.request_json,'$.target_duration_seconds'),
                func.json_extract(Row.snapshot_json,'$.title')).join(latest,and_(Row.intake_id==latest.c.intake_id,Row.revision==latest.c.revision))
                .order_by(Row.created_at.desc()).limit(50)).all()
            return [dict(intake=dict(intake_id=i,revision=r,state=s,
                request=dict(reference_url=url,target_duration_seconds=target),
                snapshot=dict(title=title) if title else None),created_at=self._stamp(created))
                for i,r,s,created,url,target,title in rows]

    def revise(self,intake_id,expected_revision,actor,*,supplied_cues=None,refresh=False):
        with self.sessions() as db:
            db.execute(text('BEGIN IMMEDIATE'));old=self._row(db,intake_id)
            if old.revision!=expected_revision:raise IntakeConflict('This reference changed; reload before creating a revision.')
            if old.state=='pending':raise IntakeConflict('Cancel or finish the pending intake before revising it.')
            request=ReferenceIntakeRequest.model_validate_json(old.request_json)
            if refresh:
                # A fresh capture asks the public source again; supplied text
                # remains available only in its immutable earlier revision.
                request=request.model_copy(update={'supplied_cues': ()})
            if supplied_cues is not None:
                raw=request.model_dump(mode='python');raw['supplied_cues']=supplied_cues;request=ReferenceIntakeRequest.model_validate(raw)
            row=self._new(request,intake_id,old.revision+1,force_refresh=refresh)
            db.add(row);self._event(db,row,'revision_created',actor,previous_revision=old.revision,refresh=refresh,transcript_supplied=supplied_cues is not None)
            db.commit();return self.get(intake_id,row.revision)

    def cancel(self,intake_id,revision,actor):
        with self.sessions() as db:
            db.execute(text('BEGIN IMMEDIATE'));row=self._row(db,intake_id)
            if row.revision!=revision or row.state!='pending':raise IntakeConflict('Only the current pending revision can be cancelled.')
            row.state='failed';row.failure_code='cancelled';row.message='Reference intake was cancelled.'
            row.finished_at=self.clock();row.claim_token=None;row.claim_owner=None;row.lease_expires_at=None
            self._event(db,row,'intake_cancelled',actor);db.commit();return self.get(intake_id,revision)

    def claim(self,owner,lease_seconds=120):
        now=self.clock()
        with self.sessions() as db:
            db.execute(text('BEGIN IMMEDIATE'))
            candidates=db.scalars(select(Row).where(Row.state=='pending').order_by(Row.created_at).limit(100)).all()
            for row in candidates:
                expiry=row.lease_expires_at
                if expiry is not None and expiry.replace(tzinfo=UTC)>now:continue
                active=db.scalar(select(Row.row_id).where(Row.capture_key==row.capture_key,Row.state=='pending',Row.lease_expires_at>now,Row.row_id!=row.row_id).limit(1))
                if active:continue
                row.claim_owner=owner;row.claim_token=uuid4().hex;row.lease_expires_at=now+timedelta(seconds=lease_seconds)
                self._event(db,row,'capture_claimed',owner)
                db.commit();return dict(row_id=row.row_id,intake_id=row.intake_id,revision=row.revision,token=row.claim_token,
                                        request=ReferenceIntakeRequest.model_validate_json(row.request_json),capture_key=row.capture_key,force_refresh=row.force_refresh)
            db.commit();return None

    def owns(self,claim):
        with self.sessions() as db:
            row=db.get(Row,claim['row_id'])
            return bool(row and row.state=='pending' and row.claim_token==claim['token'] and row.lease_expires_at and row.lease_expires_at.replace(tzinfo=UTC)>self.clock())

    def cached_snapshot(self,claim):
        if claim['force_refresh']:return None
        with self.sessions() as db:
            row=db.scalar(select(Row).where(Row.capture_key==claim['capture_key'],Row.snapshot_json.is_not(None),or_(Row.state=='ready',Row.failure_code.in_(['captions_unavailable','language_mismatch']))).order_by(Row.finished_at.desc()).limit(1))
            return dict(snapshot=self._view(row).snapshot,code=row.failure_code,message=row.message) if row else None

    def previous_snapshot(self,claim):
        with self.sessions() as db:
            row=db.scalar(select(Row).where(Row.intake_id==claim['intake_id'],Row.revision<claim['revision'],Row.snapshot_json.is_not(None)).order_by(Row.revision.desc()).limit(1))
            return self._view(row).snapshot if row else None

    def finish(self,claim,*,snapshot=None,failure=None,cache_hit=False):
        with self.sessions() as db:
            db.execute(text('BEGIN IMMEDIATE'));row=db.get(Row,claim['row_id'])
            if not row or row.state!='pending' or row.claim_token!=claim['token'] or row.lease_expires_at.replace(tzinfo=UTC)<=self.clock():return False
            if snapshot is not None:
                request=ReferenceIntakeRequest.model_validate_json(row.request_json)
                if snapshot.reference_url!=request.reference_url:raise ValueError('Captured reference URL differs from request')
                row.snapshot_json=snapshot.model_dump_json();row.snapshot_sha256=hashlib.sha256(row.snapshot_json.encode()).hexdigest()
                if snapshot.transcript_origin=='unavailable':
                    row.state='needs_input';row.failure_code=failure.code if failure else 'captions_unavailable';row.message=str(failure)[:500] if failure else snapshot.limitations[-1]
                elif snapshot.language.casefold()!=request.language.casefold():
                    row.state='needs_input';row.failure_code='language_mismatch';row.message='Captured language differs from requested language; supply the requested transcript.'
                else:row.state='ready'
            else:
                row.state='failed';row.failure_code=failure.code;row.message=str(failure)[:500]
            owner=row.claim_owner
            row.finished_at=self.clock();row.cache_hit=cache_hit;row.claim_owner=None;row.claim_token=None;row.lease_expires_at=None
            self._event(db,row,'capture_'+row.state,owner or 'worker',cache_hit=cache_hit,failure_code=row.failure_code)
            db.commit();return True
