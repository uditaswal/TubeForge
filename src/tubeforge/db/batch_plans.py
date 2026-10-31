"""Batch intake using ordinary backlog topics and transactional idempotency."""
import json
from datetime import UTC, datetime

from sqlalchemy import select, text
from tubeforge.batch_plans import BatchShort
from tubeforge.db.models import TopicRecord


class BatchPlanRepository:
    def __init__(self, session_factory):
        self.sessions = session_factory

    def import_shorts(self, shorts: list[BatchShort], *, commit: bool = False):
        results = []
        with self.sessions() as session:
            # Serialize intake with scheduler reservation and concurrent imports.
            session.execute(text("BEGIN IMMEDIATE"))
            for short in shorts:
                key = "batch-" + short.id
                payload = short.model_dump(mode="json")
                row = session.get(TopicRecord, key)
                existing = json.loads(row.options_json).get("batch_plan") if row else None
                if row and existing == payload:
                    action = "skipped"
                elif row and (row.generation_job_id or row.status != "ready" or existing is None):
                    action = "conflict"
                else:
                    action = "updated" if row else "created"
                    if commit:
                        now = datetime.now(UTC)
                        if row is None:
                            row = TopicRecord(id=key, title=short.title, notes=short.concept, priority=0, status="ready", options_json="{}", attempts=0, created_at=now, updated_at=now)
                            session.add(row)
                        row.title, row.notes = short.title, short.concept
                        options = json.loads(row.options_json)
                        options["batch_plan"] = payload
                        row.options_json = json.dumps(options, sort_keys=True)
                        row.updated_at = now
                results.append({"id": short.id, "action": action, "short": payload})
            if commit:
                session.commit()
            else:
                session.rollback()
        return results

    def list(self):
        with self.sessions() as session:
            rows = session.scalars(select(TopicRecord).where(TopicRecord.id.like("batch-%")).order_by(TopicRecord.created_at, TopicRecord.id))
            return [{"id": row.id, "short": json.loads(row.options_json)["batch_plan"], "status": row.status, "job_id": row.generation_job_id} for row in rows if "batch_plan" in json.loads(row.options_json)]

    def for_job(self, job_id):
        with self.sessions() as session:
            row = session.scalar(select(TopicRecord).where(TopicRecord.generation_job_id == job_id))
            if row and 'batch_plan' in json.loads(row.options_json):
                return json.loads(row.options_json)
        return None

    def save_qa(self, job_id, qa, *, owner):
        from tubeforge.db.models import PipelineJobRecord
        with self.sessions() as session:
            session.execute(text('BEGIN IMMEDIATE'))
            job = session.get(PipelineJobRecord, job_id)
            if job is None or job.claim_owner != owner:
                raise ValueError('worker ownership lost while recording QA')
            row = session.scalar(select(TopicRecord).where(TopicRecord.generation_job_id == job_id))
            if row:
                options = json.loads(row.options_json)
                options['batch_qa'] = qa
                row.options_json = json.dumps(options, sort_keys=True)
            session.commit()

    def produce(self, ids, build_request):
        from hashlib import sha256
        from tubeforge.db.repositories import TopicRepository
        topics = TopicRepository(self.sessions)
        selected = {item['short']['id']: item for item in self.list()}
        if any(key not in selected for key in ids):
            raise ValueError('unknown short id')
        # Validate the complete selection before mutating any backlog rows.
        requests = {key: build_request(BatchShort.model_validate(selected[key]['short'])) for key in ids}
        results = []
        for key in ids:
            item = selected[key]
            job_id = 'batch-' + sha256(key.encode()).hexdigest()[:48]
            job = topics.reserve_and_create_job(topic_id=item['id'], scheduler_id='batch-operator', job_id=job_id, request=requests[key], lease_seconds=600)
            existing = topics.get(item['id'])
            results.append({'id': key, 'job_id': job.id if job else existing.generation_job_id, 'action': 'created' if job else 'skipped'})
        return results
