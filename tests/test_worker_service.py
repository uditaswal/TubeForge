from __future__ import annotations

from datetime import UTC, datetime
import logging
from pathlib import Path

from tubeforge.core.config import DatabaseConfig, WorkerConfig
from tubeforge.db.models import Base
from tubeforge.db.repositories import Artifact, ArtifactRepository, HeavyWorkLeaseRepository, JobEventRepository, JobRepository, PipelineJob
from tubeforge.db.session import create_database
from tubeforge.domain.contracts import ContentRequest, SourceReference
from tubeforge.domain.states import JobState
from tubeforge.workers.service import WorkerService


def _request() -> ContentRequest:
    return ContentRequest(
        topic="Rain", angle="Explainer", target_duration_seconds=60, language="en-IN",
        audience="general", prompt_version="test-v1",
        sources=(SourceReference(source_id="source-1", url="https://example.invalid/rain", title="Rain"),),
    )


class _AdvancingOrchestrator:
    def __init__(self, jobs: JobRepository) -> None:
        self.jobs = jobs
        self.events = JobEventRepository(jobs._session_factory)
        self.calls = 0

    def run(self, job_id: str, **_: object) -> PipelineJob:
        self.calls += 1
        return self.jobs.update_state(job_id, JobState.SCRIPT_APPROVAL_REQUIRED)


def test_worker_claims_eligible_job_and_skips_waiting_or_terminal_states(tmp_path: Path) -> None:
    database = create_database(DatabaseConfig(url=f"sqlite:///{tmp_path / 'worker.db'}"))
    Base.metadata.create_all(database.engine)
    jobs = JobRepository(database.session_factory)
    orchestrator = _AdvancingOrchestrator(jobs)
    worker = WorkerService("worker-1", jobs, orchestrator, WorkerConfig(), clock=lambda: datetime.now(UTC))
    try:
        jobs.create("eligible", _request())
        assert worker.run_once().state is JobState.SCRIPT_APPROVAL_REQUIRED
        assert orchestrator.calls == 1

        for index, state in enumerate((
            JobState.SCRIPT_APPROVAL_REQUIRED, JobState.PREVIEW_READY,
            JobState.PUBLICATION_APPROVAL_REQUIRED, JobState.PUBLICATION_READY, JobState.PUBLISHED,
        )):
            job_id = f"blocked-{index}"
            jobs.create(job_id, _request())
            jobs.update_state(job_id, state)
        assert worker.run_once() is None
        assert orchestrator.calls == 1
    finally:
        database.dispose()


def test_worker_emits_structured_claim_and_approval_wait_logs(tmp_path: Path, caplog) -> None:
    database = create_database(DatabaseConfig(url=f"sqlite:///{tmp_path / 'logs.db'}"))
    Base.metadata.create_all(database.engine)
    jobs = JobRepository(database.session_factory)
    worker = WorkerService("worker-logs", jobs, _AdvancingOrchestrator(jobs), WorkerConfig())
    try:
        jobs.create("logged", _request())
        caplog.set_level(logging.INFO, logger="tubeforge.workers.service")
        assert worker.run_once().state is JobState.SCRIPT_APPROVAL_REQUIRED
        messages = "\n".join(record.message for record in caplog.records)
        assert '"event": "job_claimed"' in messages
        assert '"event": "waiting_for_approval"' in messages
        assert [event.event_type for event in worker.orchestrator.events.list_for_job("logged")] == ["job_claimed", "waiting_for_approval"]
    finally:
        database.dispose()


class _Clock:
    def __init__(self, value: datetime) -> None:
        self.value = value

    def __call__(self) -> datetime:
        return self.value

    def advance(self, seconds: int) -> None:
        from datetime import timedelta
        self.value += timedelta(seconds=seconds)


def test_heartbeat_renews_job_and_global_leases_beyond_original_expiry(tmp_path: Path) -> None:
    from tubeforge.workers.service import _ExecutionLease
    database = create_database(DatabaseConfig(url=f"sqlite:///{tmp_path / 'renewal.db'}")); Base.metadata.create_all(database.engine)
    clock = _Clock(datetime(2026, 8, 17, tzinfo=UTC)); jobs = JobRepository(database.session_factory)
    try:
        jobs.create("job", _request())
        assert jobs.claim_oldest_eligible("worker-a", now=clock(), lease_seconds=300)
        heavy = HeavyWorkLeaseRepository(database.session_factory)
        guard = _ExecutionLease("worker-a", "job", jobs, heavy, WorkerConfig(lease_seconds=300, heartbeat_seconds=60), clock)
        assert guard.acquire()
        clock.advance(240)
        assert guard.check()
        clock.advance(240)
        assert guard.check()
        assert jobs.owns_lease("job", "worker-a", now=clock())
        assert heavy.owns("worker-a", now=clock())
    finally:
        database.dispose()


def test_global_heavy_work_admission_blocks_second_worker(tmp_path: Path) -> None:
    database = create_database(DatabaseConfig(url=f"sqlite:///{tmp_path / 'contention.db'}")); Base.metadata.create_all(database.engine)
    clock = _Clock(datetime(2026, 8, 17, tzinfo=UTC)); jobs = JobRepository(database.session_factory)
    class Primary:
        def __init__(self) -> None: self.secondary: WorkerService | None = None; self.calls = 0
        def run(self, job_id: str, **_: object) -> PipelineJob:
            self.calls += 1
            assert self.secondary is not None and self.secondary.run_once() is None
            return jobs.update_state(job_id, JobState.SCRIPT_APPROVAL_REQUIRED)
    class Secondary:
        def __init__(self) -> None: self.calls = 0
        def run(self, job_id: str, **_: object) -> PipelineJob:
            self.calls += 1
            return jobs.update_state(job_id, JobState.SCRIPT_APPROVAL_REQUIRED)
    try:
        jobs.create("first", _request()); jobs.create("second", _request())
        primary, secondary = Primary(), Secondary()
        second_worker = WorkerService("worker-b", jobs, secondary, WorkerConfig(), clock=clock)
        primary.secondary = second_worker
        assert WorkerService("worker-a", jobs, primary, WorkerConfig(), clock=clock).run_once().id == "first"
        assert primary.calls == 1 and secondary.calls == 0
        assert jobs.get("second").claim_owner is None
    finally:
        database.dispose()


def test_crashed_worker_is_reclaimed_only_after_both_leases_expire(tmp_path: Path) -> None:
    database = create_database(DatabaseConfig(url=f"sqlite:///{tmp_path / 'reclaim.db'}")); Base.metadata.create_all(database.engine)
    clock = _Clock(datetime(2026, 8, 17, tzinfo=UTC)); jobs = JobRepository(database.session_factory); heavy = HeavyWorkLeaseRepository(database.session_factory)
    try:
        jobs.create("job", _request())
        assert jobs.claim_oldest_eligible("worker-a", now=clock(), lease_seconds=300)
        assert heavy.acquire("worker-a", now=clock(), lease_seconds=300)
        clock.advance(301)
        orchestrator = _AdvancingOrchestrator(jobs)
        assert WorkerService("worker-b", jobs, orchestrator, WorkerConfig(), clock=clock, heavy_work=heavy).run_once().state is JobState.SCRIPT_APPROVAL_REQUIRED
        assert orchestrator.calls == 1
    finally:
        database.dispose()


def test_stale_worker_cannot_promote_checkpoint_or_state(tmp_path: Path) -> None:
    database = create_database(DatabaseConfig(url=f"sqlite:///{tmp_path / 'stale.db'}")); Base.metadata.create_all(database.engine)
    clock = _Clock(datetime(2026, 8, 17, tzinfo=UTC)); jobs = JobRepository(database.session_factory); artifacts = ArtifactRepository(database.session_factory)
    try:
        jobs.create("job", _request())
        assert jobs.claim_oldest_eligible("worker-a", now=clock(), lease_seconds=300)
        clock.advance(301)
        assert jobs.claim_oldest_eligible("worker-b", now=clock(), lease_seconds=300)
        artifact = Artifact("job", JobState.CONTENT_GENERATING, "content_package", str(tmp_path / "package.json"), "a" * 64, {})
        assert artifacts.save_if_claimed(artifact, "worker-a", now=clock()) is None
        assert jobs.update_state_if_claimed("job", "worker-a", now=clock(), state=JobState.CONTENT_READY) is None
        assert jobs.get("job").state is JobState.TOPIC_CREATED
    finally:
        database.dispose()
