"""Reliable, synchronous single-job worker with lease recovery and retries."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import json
import logging
from typing import Callable

from tubeforge.core.config import WorkerConfig
from tubeforge.db.repositories import HeavyWorkLeaseRepository, JobRepository, PipelineJob
from tubeforge.domain.states import JobState
from tubeforge.pipeline.orchestrator import PipelineInterrupted, PipelineOrchestrator


logger = logging.getLogger(__name__)


def _event(event: str, **fields: object) -> None:
    """Emit one JSON log line so Docker can consume worker lifecycle events."""
    logger.info(json.dumps({"event": event, **fields}, sort_keys=True, default=str))


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
        _event("job_claimed", job_id=job.id, worker_id=self.worker_id, state=job.state.value)
        self._record(job.id, "job_claimed", worker_id=self.worker_id, state=job.state.value)
        guard = _ExecutionLease(self.worker_id, job.id, self.jobs, self.heavy_work, self.config, self._now)
        if not guard.acquire():
            self.jobs.release_claim(job.id, self.worker_id)
            _event("job_claim_released", job_id=job.id, worker_id=self.worker_id, reason="heavy_work_unavailable")
            self._record(job.id, "job_claim_released", reason="heavy_work_unavailable")
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
            if result.state in {JobState.SCRIPT_APPROVAL_REQUIRED, JobState.PREVIEW_READY, JobState.PUBLICATION_APPROVAL_REQUIRED}:
                _event("waiting_for_approval", job_id=result.id, state=result.state.value)
                self._record(result.id, "waiting_for_approval", state=result.state.value)
            elif result.failure_message:
                _event("job_error", job_id=result.id, state=result.state.value, error=result.failure_message)
                self._record(result.id, "job_error", state=result.state.value, error=result.failure_message)
            else:
                _event("job_finished", job_id=result.id, state=result.state.value)
                self._record(result.id, "job_finished", state=result.state.value)
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
        policy_reader = getattr(self.orchestrator, "alignment_retry_policy", None)
        alignment_policy = policy_reader(job) if callable(policy_reader) else None
        immediate, cap, transient_count = alignment_policy if alignment_policy is not None else (False, self.config.max_attempts, attempt)
        exhausted = attempt >= cap
        delay = 0 if immediate else min(self.config.retry_base_seconds * (2 ** (max(1, transient_count) - 1)), self.config.retry_max_seconds)
        result = self.jobs.schedule_retry(job.id, self.worker_id, now=self._now(), next_retry_at=self._now() + timedelta(seconds=delay), exhausted=exhausted)
        _event("job_retry_scheduled", job_id=job.id, attempt=attempt, delay_seconds=delay, exhausted=exhausted)
        self._record(job.id, "job_retry_scheduled", attempt=attempt, delay_seconds=delay, exhausted=exhausted)
        return result

    def _record(self, job_id: str, event_type: str, **details: object) -> None:
        events = getattr(self.orchestrator, "events", None)
        if events is not None:
            events.append(job_id, event_type, **details)

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
