"""Opt-in batch triggers stored in the existing schedules/run-history tables."""
import hashlib
import json
from datetime import UTC, datetime
from zoneinfo import ZoneInfo
from sqlalchemy import select, text
from tubeforge.db.models import BatchProductionControlRecord, ScheduleRecord, ScheduleRunRecord


def is_held(session):
    row = session.get(BatchProductionControlRecord, 1)
    return bool(row and row.hold)


class BatchAutomationRepository:
    def __init__(self, sessions):
        self.sessions = sessions

    def hold(self, value=None):
        with self.sessions.begin() as session:
            row = session.get(BatchProductionControlRecord, 1)
            if value is not None:
                if row is None:
                    row = BatchProductionControlRecord(id=1, hold=value)
                    session.add(row)
                else:
                    row.hold = value
            return bool(row and row.hold)

    def schedule_id(self, plan_id):
        return 'batch-auto-' + hashlib.sha256(plan_id.encode()).hexdigest()[:40]

    def get(self, plan_id):
        with self.sessions() as session:
            row = session.get(ScheduleRecord, self.schedule_id(plan_id))
            default = {'enabled': False, 'start_time': '22:00', 'timezone': 'Asia/Kolkata', 'day_offset': 1, 'next_run_at': None, 'last_run': None}
            if row:
                options = json.loads(row.options_json)
                default.update({key: options[key] for key in ['start_time', 'day_offset']})
                default.update(enabled=row.enabled, timezone=row.timezone, next_run_at=row.next_run_at.isoformat() if row.enabled and row.next_run_at else None)
                run = session.scalar(select(ScheduleRunRecord).where(ScheduleRunRecord.schedule_id == row.id).order_by(ScheduleRunRecord.started_at.desc(), ScheduleRunRecord.id.desc()).limit(1))
                if run:
                    details = json.loads(run.details_json)
                    default['last_run'] = {'state': run.state, 'started_at': run.started_at.isoformat(), 'finished_at': run.finished_at.isoformat() if run.finished_at else None, 'result': details.get('result')}
            return {'plan_id': plan_id, 'hold': is_held(session), **default}

    def configure(self, plan_id, *, enabled, start_time, timezone, day_offset, now=None):
        from tubeforge.scheduling.service import next_run
        now = now or datetime.now(UTC)
        ZoneInfo(timezone)
        hour, minute = map(int, start_time.split(':'))
        if not (0 <= hour <= 23 and 0 <= minute <= 59 and 0 <= day_offset <= 7):
            raise ValueError('invalid production time or target day offset')
        cron = f'{minute} {hour} * * *'
        with self.sessions() as session:
            session.execute(text('BEGIN IMMEDIATE'))
            row = session.get(ScheduleRecord, self.schedule_id(plan_id))
            if row is None:
                row = ScheduleRecord(id=self.schedule_id(plan_id), name='Batch production: ' + plan_id, cron=cron, timezone=timezone, enabled=enabled, options_json='{}', created_at=now, updated_at=now)
                session.add(row)
            active = session.scalar(select(ScheduleRunRecord).where(ScheduleRunRecord.schedule_id == row.id, ScheduleRunRecord.state == 'running'))
            if active:
                raise ValueError('production submission is running; use hold before changing its configuration')
            row.cron, row.timezone, row.enabled = cron, timezone, enabled
            row.options_json = json.dumps({'batch_plan_id': plan_id, 'start_time': start_time, 'day_offset': day_offset})
            row.next_run_at = next_run(cron, timezone, now) if enabled else None
            row.updated_at = now
            session.commit()
        return self.get(plan_id)
