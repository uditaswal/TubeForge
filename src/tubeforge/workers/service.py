"""Reliable, synchronous single-job worker with lease recovery and retries."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Callable

from tubeforge.core.config import WorkerConfig
from tubeforge.db.repositories import HeavyWorkLeaseRepository, JobRepository, PipelineJob
from tubeforge.domain.states import JobState
from tubeforge.pipeline.orchestrator import PipelineInterrupted, PipelineOrchestrator


class WorkerService:
    """Claim and run at most one job; all database work brackets orchestration."""

    def __init__(self, worker_id: str, jobs: JobRepository, orchestrator: PipelineOrchestrator, config: WorkerConfig = WorkerConfig(), clock: Callable[[], datetime] | None = None, heavy_work: HeavyWorkLeaseRepository | None = None) -> None:
        self.worker_id, self.jobs, self.orchestrator, self.config = worker_id, jobs, orchestrator, config
        self._clock = clock or (lambda: datetime.now(UTC))
        self.heavy_work = heavy_work or HeavyWorkLeaseRepository(jobs._session_factory)

    def run_once(self, *, interrupt_after: JobState | None = None) -> PipelineJob | None:
        """Lease one eligible job then execute without a database transaction open."""
        now = self._now()
        job = self.jobs.claim_oldest_eligible(self.worker_id, now=now, lease_seconds=self.config.lease_seconds)
        if job is None:
            return None
        guard = _ExecutionLease(self.worker_id, job.id, self.jobs, self.heavy_work, self.config, self._now)
        if not guard.acquire():
            self.jobs.release_claim(job.id, self.worker_id)
            return None
        try:
            result = self.orchestrator.run(
                job.id,
                authentication_restored=job.authentication_restored_at is not None,
                interrupt_after=interrupt_after,
                cancellation_requested=lambda: self.jobs.get(job.id).cancellation_requested_at is not None,
                ownership_check=guard.check,
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
            guard.release()
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


class _ExecutionLease:
    """Renew the job and global leases together without per-poll database writes."""

    def __init__(self, worker_id: str, job_id: str, jobs: JobRepository, heavy_work: HeavyWorkLeaseRepository, config: WorkerConfig, clock: Callable[[], datetime]) -> None:
        self.worker_id, self.job_id, self.jobs, self.heavy_work, self.config, self.clock = worker_id, job_id, jobs, heavy_work, config, clock
        self._last_heartbeat: datetime | None = None

    def acquire(self) -> bool:
        now = self.clock()
        if not self.heavy_work.acquire(self.worker_id, now=now, lease_seconds=self.config.lease_seconds):
            return False
        if not self.jobs.heartbeat(self.job_id, self.worker_id, now=now, lease_seconds=self.config.lease_seconds):
            self.heavy_work.release(self.worker_id)
            return False
        self._last_heartbeat = now
        return True

    def check(self, *, force: bool = False) -> bool:
        now = self.clock()
        if self._last_heartbeat is None or force or (now - self._last_heartbeat).total_seconds() >= self.config.heartbeat_seconds:
            if not self.jobs.heartbeat(self.job_id, self.worker_id, now=now, lease_seconds=self.config.lease_seconds):
                return False
            if not self.heavy_work.heartbeat(self.worker_id, now=now, lease_seconds=self.config.lease_seconds):
                return False
            self._last_heartbeat = now
            return True
        return self.jobs.owns_lease(self.job_id, self.worker_id, now=now) and self.heavy_work.owns(self.worker_id, now=now)

    def release(self) -> None:
        self.heavy_work.release(self.worker_id)
