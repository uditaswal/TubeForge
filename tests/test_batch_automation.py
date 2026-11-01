from datetime import UTC, datetime, timedelta
import pytest
from tubeforge.batch_plans import BatchShort
from tubeforge.core.config import DatabaseConfig
from tubeforge.db.models import Base
from tubeforge.db.session import create_database
from tubeforge.db.repositories import JobRepository, ScheduleRepository, TopicRepository
from tubeforge.db.batch_plans import BatchPlanRepository
from tubeforge.db.batch_automation import BatchAutomationRepository
from tubeforge.scheduling.service import SchedulerService
from tubeforge.domain.states import JobState
from test_batch_queue import request


@pytest.fixture
def automation(tmp_path):
    db = create_database(DatabaseConfig(url=f"sqlite:///{tmp_path / 'automation.db'}"))
    Base.metadata.create_all(db.engine)
    plans = BatchPlanRepository(db.session_factory)
    plans.import_shorts([BatchShort(id=str(i), title=str(i), concept='Concept', beats=[{'t': 0, 'point': 'Hook'}], publish_at='2026-11-02T09:00:00+05:30') for i in range(3)], commit=True, plan_id='week')
    control = BatchAutomationRepository(db.session_factory)
    now = datetime(2026, 11, 1, 16, 0, tzinfo=UTC)  # 21:30 IST
    control.configure('week', enabled=True, start_time='22:00', timezone='Asia/Kolkata', day_offset=1, now=now)
    scheduler = SchedulerService(ScheduleRepository(db.session_factory), TopicRepository(db.session_factory), scheduler_id='test')
    scheduler.batch_request_factory = request
    yield db, plans, control, scheduler, now
    db.dispose()


def test_not_due_due_local_offset_double_fire_and_no_approval(automation):
    db, plans, control, scheduler, now = automation
    assert control.get('unknown')['enabled'] is False
    assert control.get('week')['next_run_at'] == '2026-11-01T22:00:00+05:30'
    assert scheduler.tick(now=now) == []
    result = scheduler.tick(now=now + timedelta(minutes=30))[0]
    assert result['state'] == 'done' and len(result['items']) == 3
    assert result['target_day'] == '2026-11-02'
    assert scheduler.tick(now=now + timedelta(minutes=30)) == []
    jobs = JobRepository(db.session_factory).list_recent()
    assert len(jobs) == 3 and all(job.request.review_mode == 'manual' for job in jobs)
    assert control.get('week')['last_run']['state'] == 'done'


def test_hold_blocks_scheduled_manual_creation_and_worker_claims(automation):
    db, plans, control, scheduler, now = automation
    control.hold(True)
    assert scheduler.tick(now=now + timedelta(minutes=30))[0]['reason'] == 'hold'
    with pytest.raises(ValueError, match='hold'):
        plans.produce(['0'], request)
    control.hold(False)
    plans.produce(['0'], request)
    control.hold(True)
    assert JobRepository(db.session_factory).claim_oldest_eligible('worker', now=now, lease_seconds=60) is None
    control.hold(False)
    assert JobRepository(db.session_factory).claim_oldest_eligible('worker', now=now, lease_seconds=60) is not None


def test_restart_mid_submission_reuses_jobs_and_recovers_lease(automation):
    db, plans, control, scheduler, now = automation
    class Killed(BaseException):
        pass
    calls = []
    def interrupted(short):
        calls.append(short.id)
        if short.id == '1':
            raise Killed()
        return request(short)
    scheduler.batch_request_factory = interrupted
    with pytest.raises(Killed):
        scheduler.tick(now=now + timedelta(minutes=30))
    assert len(JobRepository(db.session_factory).list_recent()) == 1
    assert control.get('week')['last_run']['state'] == 'running'
    scheduler.batch_request_factory = request
    assert scheduler.tick(now=now + timedelta(minutes=31))[0]['state'] == 'running'
    result = scheduler.tick(now=now + timedelta(minutes=36))[0]
    assert result['state'] == 'done'
    assert result['items'][0]['action'] == 'skipped'
    assert len(JobRepository(db.session_factory).list_recent()) == 3


def test_existing_exhausted_job_not_replaced(automation):
    db, plans, control, scheduler, now = automation
    jobs = JobRepository(db.session_factory)
    original = plans.produce(['0'], request)[0]['job_id']
    jobs.update_state(original, JobState.FAILED_VALIDATION, failure_message='two-attempt allowance exhausted')
    result = scheduler.tick(now=now + timedelta(minutes=30))[0]
    assert result['items'][0]['job_id'] == original
    assert result['items'][0]['action'] == 'skipped'
    assert result['items'][0]['status'] == 'needs operator decision'
    assert jobs.get(original).failure_message == 'two-attempt allowance exhausted'


def test_hold_during_submission_stops_remaining_creations_and_can_resume(automation):
    db, plans, control, scheduler, now = automation
    calls = []
    def pausing(short):
        calls.append(short.id)
        if short.id == '1':
            control.hold(True)
        return request(short)
    scheduler.batch_request_factory = pausing
    result = scheduler.tick(now=now + timedelta(minutes=30))[0]
    assert result['state'] == 'pending'
    assert len(JobRepository(db.session_factory).list_recent()) == 1
    control.hold(False)
    scheduler.batch_request_factory = request
    assert scheduler.tick(now=now + timedelta(minutes=31))[0]['state'] == 'done'
    assert len(JobRepository(db.session_factory).list_recent()) == 3


def test_hold_migration_upgrades_existing_schema(tmp_path):
    from argparse import Namespace
    from pathlib import Path
    from alembic import command
    from alembic.config import Config
    root = Path(__file__).resolve().parents[1]
    path = tmp_path / 'migration.db'
    config = Config(str(root / 'alembic.ini'))
    config.set_main_option('script_location', str(root / 'migrations'))
    config.cmd_opts = Namespace(x=[f'database_url=sqlite:///{path}'])
    command.upgrade(config, '20261022_0030')
    command.upgrade(config, 'head')
    database = create_database(DatabaseConfig(url=f'sqlite:///{path}'))
    try:
        control = BatchAutomationRepository(database.session_factory)
        assert control.hold() is False
        assert control.hold(True) is True
    finally:
        database.dispose()
