"""Reliable, synchronous single-job worker with lease recovery and retries."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Callable

from tubeforge.core.config import WorkerConfig
from tubeforge.db.repositories import JobRepository, PipelineJob
from tubeforge.domain.states import JobState
from tubeforge.pipeline.orchestrator import PipelineInterrupted, PipelineOrchestrator


class WorkerService:
    """Claim and run at most one job; all database work brackets orchestration."""

    def __init__(self, worker_id: str, jobs: JobRepository, orchestrator: PipelineOrchestrator, config: WorkerConfig = WorkerConfig(), clock: Callable[[], datetime] | None = None) -> None:
        self.worker_id, self.jobs, self.orchestrator, self.config = worker_id, jobs, orchestrator, config
        self._clock = clock or (lambda: datetime.now(UTC))

    def run_once(self, *, interrupt_after: JobState | None = None) -> PipelineJob | None:
        """Lease one eligible job then execute without a database transaction open."""
        now = self._now()
        job = self.jobs.claim_oldest_eligible(self.worker_id, now=now, lease_seconds=self.config.lease_seconds)
        if job is None:
            return None
        try:
            result = self.orchestrator.run(
                job.id,
                authentication_restored=job.authentication_restored_at is not None,
                interrupt_after=interrupt_after,
                cancellation_requested=lambda: self.jobs.get(job.id).cancellation_requested_at is not None,
            )
            if result.state is JobState.FAILED_RETRYABLE:
                return self._schedule_retry(result)
            if result.state is JobState.PUBLICATION_VERIFICATION_PENDING:
                return self.jobs.defer_verification(result.id, self.worker_id, now=self._now(), next_retry_at=self._now() + timedelta(seconds=self.orchestrator.verification_config.pending_poll_seconds))
            return result
        except PipelineInterrupted:
            # Simulates process death: leave the lease so another worker can recover it.
            raise
        finally:
            latest = self.jobs.get(job.id)
            if latest.claim_owner == self.worker_id and latest.state is not JobState.FAILED_RETRYABLE:
                self.jobs.release_claim(job.id, self.worker_id)

    def _schedule_retry(self, job: PipelineJob) -> PipelineJob:
        attempt = job.attempt_count + 1
        exhausted = attempt >= self.config.max_attempts
        delay = min(self.config.retry_base_seconds * (2 ** (attempt - 1)), self.config.retry_max_seconds)
        return self.jobs.schedule_retry(job.id, self.worker_id, now=self._now(), next_retry_at=self._now() + timedelta(seconds=delay), exhausted=exhausted)

    def _now(self) -> datetime:
        value = self._clock()
        return value if value.tzinfo else value.replace(tzinfo=UTC)
