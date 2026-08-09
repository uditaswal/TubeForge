from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from tubeforge.core.config import DatabaseConfig, WorkerConfig
from tubeforge.db.models import Base
from tubeforge.db.repositories import JobRepository, PipelineJob
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
            JobState.FINAL_READY, JobState.PUBLISHED,
        )):
            job_id = f"blocked-{index}"
            jobs.create(job_id, _request())
            jobs.update_state(job_id, state)
        assert worker.run_once() is None
        assert orchestrator.calls == 1
    finally:
        database.dispose()
