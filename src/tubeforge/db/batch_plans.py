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
