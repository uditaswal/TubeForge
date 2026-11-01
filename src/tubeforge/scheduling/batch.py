"""Restart-safe batch submission dispatched by the existing scheduler tick."""
import json
from datetime import UTC, datetime, timedelta
from uuid import uuid4
from zoneinfo import ZoneInfo
from sqlalchemy import select, text
from tubeforge.db.models import ScheduleRecord, ScheduleRunRecord
from tubeforge.db.batch_automation import is_held
from tubeforge.db.batch_plans import BatchPlanRepository


def utc(value):
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def run_batch_schedule(sessions, schedule_id, build_request, *, now, run_key=None):
    from tubeforge.scheduling.service import next_run
    repo = BatchPlanRepository(sessions)
    token = uuid4().hex
    with sessions() as session:
        session.execute(text('BEGIN IMMEDIATE'))
        schedule = session.get(ScheduleRecord, schedule_id)
        if not schedule or not schedule.enabled:
            return {'state': 'pending', 'reason': 'disabled'}
        if is_held(session):
            return {'state': 'pending', 'reason': 'hold'}
        if not schedule.next_run_at or utc(schedule.next_run_at) > utc(now):
            return {'state': 'pending', 'reason': 'not due'}
        options = json.loads(schedule.options_json)
        key = run_key or utc(schedule.next_run_at).isoformat()
        run = session.scalar(select(ScheduleRunRecord).where(ScheduleRunRecord.schedule_id == schedule_id, ScheduleRunRecord.run_key == key))
        if run and run.state in {'done', 'failed'}:
            return {'state': run.state, 'duplicate': True, **json.loads(run.details_json).get('result', {})}
        details = json.loads(run.details_json) if run else {}
        if run and run.state == 'running' and datetime.fromisoformat(details['lease_until']) > utc(now):
            return {'state': 'running'}
        if run is None:
            zone = ZoneInfo(schedule.timezone)
            day = (utc(schedule.next_run_at).astimezone(zone) + timedelta(days=options['day_offset'])).date()
            ids = []
            for item in repo.list():
                stamp = item['short'].get('publish_at')
                if item.get('plan_id', 'default') != options['batch_plan_id'] or not stamp:
                    continue
                planned = datetime.fromisoformat(stamp)
                planned = planned.replace(tzinfo=zone) if planned.tzinfo is None else planned.astimezone(zone)
                if planned.date() == day:
                    ids.append(item['short']['id'])
            details = {'ids': ids, 'target_day': day.isoformat()}
            run = ScheduleRunRecord(id=uuid4().hex, schedule_id=schedule_id, run_key=key, state='running', details_json='{}', started_at=now)
            session.add(run)
        details.update(owner=token, lease_until=(utc(now) + timedelta(minutes=5)).isoformat())
        run.state, run.details_json = 'running', json.dumps(details)
        run_id = run.id
        session.commit()
    results = []
    try:
        for short_id in details['ids']:
            # Reservation validates this run token and the global hold atomically.
            results.extend(repo.produce([short_id], build_request, batch_run=(run_id, token, utc(now))))
        from tubeforge.db.repositories import JobRepository
        jobs = JobRepository(sessions)
        for item in results:
            if item.get('job_id'):
                job = jobs.get(item['job_id'])
                item['status'] = 'needs operator decision' if job.failure_message and 'exhaust' in job.failure_message.lower() else job.state.value
        result = {'items': results, 'target_day': details['target_day']}
        state = 'done'
    except Exception as error:
        state = 'pending' if 'hold' in str(error).lower() else 'failed'
        result = {'items': results, 'error': str(error), 'target_day': details['target_day']}
    with sessions() as session:
        session.execute(text('BEGIN IMMEDIATE'))
        run = session.get(ScheduleRunRecord, run_id)
        latest = json.loads(run.details_json)
        if latest.get('owner') != token:
            return {'state': 'running', 'reason': 'ownership changed'}
        latest['result'] = result
        run.details_json, run.state = json.dumps(latest), state
        if state != 'pending':
            run.finished_at = now
            schedule = session.get(ScheduleRecord, schedule_id)
            schedule.last_run_at = now
            schedule.next_run_at = next_run(schedule.cron, schedule.timezone, now)
        session.commit()
    return {'state': state, **result}
