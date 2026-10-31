from datetime import UTC, datetime, timedelta
from pathlib import Path
import pytest
from tubeforge.batch_plans import BatchShort
from tubeforge.core.config import DatabaseConfig, WorkerConfig
from tubeforge.db.models import Base
from tubeforge.db.session import create_database
from tubeforge.db.batch_plans import BatchPlanRepository
from tubeforge.db.repositories import JobRepository, JobEventRepository
from tubeforge.domain.contracts import ContentRequest, SourceReference
from tubeforge.domain.states import JobState
from tubeforge.workers.service import WorkerService
from tubeforge.pipeline.orchestrator import PipelineInterrupted


def request(short):
    return ContentRequest(topic=short.title, angle=short.concept, target_duration_seconds=60, language='en', audience='general', prompt_version='test-v1', sources=(SourceReference(source_id='operator', url='https://local.invalid/notes', title='Unverified notes'),))


@pytest.fixture
def queue(tmp_path):
    db = create_database(DatabaseConfig(url=f"sqlite:///{tmp_path / 'queue.db'}"))
    Base.metadata.create_all(db.engine)
    repo = BatchPlanRepository(db.session_factory)
    repo.import_shorts([BatchShort(id=str(i), title=str(i), concept='Concept', beats=[{'t': 0, 'point': 'Hook'}]) for i in range(3)], commit=True)
    jobs = JobRepository(db.session_factory)
    yield db, repo, jobs
    db.dispose()


class Stub:
    def __init__(self, jobs, root):
        self.jobs = jobs
        self.events = JobEventRepository(jobs._session_factory)
        self.artifact_root = root
        self.calls = []
        self.interrupt = False
        self.fail = False
        self.exhaust = False

    def run(self, job_id, cancellation_requested, ownership_check, **kwargs):
        assert ownership_check(force=True)
        self.calls.append(job_id)
        if self.interrupt:
            self.interrupt = False
            raise PipelineInterrupted('stub process death')
        if cancellation_requested():
            return self.jobs.update_state(job_id, JobState.CANCELLED)
        if self.fail and len(self.calls) == 2:
            return self.jobs.update_state(job_id, JobState.FAILED_VALIDATION, failure_message='two-attempt allowance exhausted' if self.exhaust else 'stub failure')
        return self.jobs.update_state(job_id, JobState.FINAL_READY)


def test_three_jobs_fifo_failure_does_not_block_and_reclick_no_duplicates(queue, tmp_path, monkeypatch):
    db, repo, jobs = queue
    items = repo.produce(['0', '1', '2'], request)
    assert all(x['action'] == 'created' for x in items)
    assert all(x['action'] == 'skipped' for x in repo.produce(['0', '1', '2'], request))
    stub = Stub(jobs, tmp_path)
    stub.fail = stub.exhaust = True
    worker = WorkerService('worker', jobs, stub)
    monkeypatch.setattr(worker, '_batch_qa', lambda job, guard: repo.save_qa(job.id, {'exit_code': 0, 'output': 'stub'}, owner=worker.worker_id))
    results = [worker.run_once() for _ in range(3)]
    assert stub.calls == [x['job_id'] for x in items]
    assert [r.state for r in results] == [JobState.FINAL_READY, JobState.FAILED_VALIDATION, JobState.FINAL_READY]
    assert 'exhausted' in results[1].failure_message
    assert worker.run_once() is None  # Never enters publishing.


def test_restart_reclaims_same_job_and_preserves_queue(queue, tmp_path, monkeypatch):
    db, repo, jobs = queue
    items = repo.produce(['0', '1', '2'], request)
    stub = Stub(jobs, tmp_path)
    stub.interrupt = True
    now = datetime.now(UTC)
    worker = WorkerService('old', jobs, stub, clock=lambda: now)
    monkeypatch.setattr(worker, '_batch_qa', lambda job, guard: repo.save_qa(job.id, {'exit_code': 0, 'output': 'stub'}, owner=worker.worker_id))
    with pytest.raises(PipelineInterrupted):
        worker.run_once()
    restarted = WorkerService('new', jobs, stub, clock=lambda: now + timedelta(minutes=10))
    monkeypatch.setattr(restarted, '_batch_qa', lambda job, guard: repo.save_qa(job.id, {'exit_code': 0, 'output': 'stub'}, owner=restarted.worker_id))
    assert restarted.run_once().id == items[0]['job_id']
    assert restarted.run_once().id == items[1]['job_id']
    assert len(jobs.list_recent()) == 3


def test_cancelled_short_does_not_block_next(queue, tmp_path, monkeypatch):
    db, repo, jobs = queue
    items = repo.produce(['0', '1'], request)
    jobs.request_cancellation(items[0]['job_id'], now=datetime.now(UTC))
    worker = WorkerService('worker', jobs, Stub(jobs, tmp_path))
    monkeypatch.setattr(worker, '_batch_qa', lambda job, guard: repo.save_qa(job.id, {'exit_code': 0, 'output': 'stub'}, owner=worker.worker_id))
    assert worker.run_once().state == JobState.CANCELLED
    assert worker.run_once().id == items[1]['job_id']


def test_live_claim_blocks_other_batch_worker_then_expiry_recovers(queue):
    db, repo, jobs = queue
    items = repo.produce(['0', '1', '2'], request)
    now = datetime.now(UTC)
    assert jobs.claim_oldest_eligible('killed', now=now, lease_seconds=30).id == items[0]['job_id']
    assert jobs.claim_oldest_eligible('other', now=now, lease_seconds=30) is None
    assert jobs.claim_oldest_eligible('restart', now=now + timedelta(seconds=31), lease_seconds=30).id == items[0]['job_id']


def test_manual_approval_wait_blocks_later_batch_jobs(queue):
    db, repo, jobs = queue
    first = repo.produce(['0', '1'], request)[0]['job_id']
    jobs.update_state(first, JobState.SCRIPT_APPROVAL_REQUIRED)
    assert jobs.claim_oldest_eligible('other', now=datetime.now(UTC), lease_seconds=30) is None


def test_qa_missing_artifacts_is_recorded_without_rendering(queue, tmp_path):
    db, repo, jobs = queue
    job_id = repo.produce(['0'], request)[0]['job_id']
    result = WorkerService('qa-worker', jobs, Stub(jobs, tmp_path)).run_once()
    assert result.state == JobState.FINAL_READY
    qa = repo.for_job(job_id)['batch_qa']
    assert qa['exit_code'] == 2
    assert any(e.event_type == 'batch_qa_recorded' for e in JobEventRepository(db.session_factory).list_for_job(job_id))


def test_restart_after_final_checkpoint_runs_qa_without_publication(queue, tmp_path):
    db, repo, jobs = queue
    first = repo.produce(['0'], request)[0]['job_id']
    jobs.update_state(first, JobState.FINAL_READY)
    stub = Stub(jobs, tmp_path)
    worker = WorkerService('restarted', jobs, stub)
    assert worker.run_once().id == first
    assert stub.calls == []
    assert repo.for_job(first)['batch_qa']['exit_code'] == 2
    assert worker.run_once() is None


def test_unexpected_middle_renderer_exception_does_not_stall_batch(queue, tmp_path, monkeypatch):
    db, repo, jobs = queue
    items = repo.produce(['0', '1', '2'], request)
    stub = Stub(jobs, tmp_path)
    normal = stub.run
    def run(job_id, **kwargs):
        if job_id == items[1]['job_id']:
            raise RuntimeError('stub renderer crashed')
        return normal(job_id, **kwargs)
    stub.run = run
    worker = WorkerService('worker', jobs, stub)
    monkeypatch.setattr(worker, '_batch_qa', lambda job, guard: repo.save_qa(job.id, {'exit_code': 0, 'output': 'stub'}, owner=worker.worker_id))
    assert worker.run_once().state == JobState.FINAL_READY
    assert worker.run_once().state == JobState.FAILED_VALIDATION
    assert worker.run_once().id == items[2]['job_id']


@pytest.mark.parametrize('state', [JobState.FAILED_EXHAUSTED, JobState.FAILED_VALIDATION, JobState.CANCELLED])
def test_terminal_checkpoint_recovers_missing_qa_without_rerunning_job(queue, tmp_path, state):
    db, repo, jobs = queue
    job_id = repo.produce(['0'], request)[0]['job_id']
    jobs.update_state(job_id, state)
    stub = Stub(jobs, tmp_path)
    worker = WorkerService('restarted', jobs, stub)
    assert worker.run_once().state == state
    assert stub.calls == []
    assert repo.for_job(job_id)['batch_qa']['exit_code'] == 2
    assert worker.run_once() is None
