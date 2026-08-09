"""Pure deterministic Phase 1 pipeline transition policy."""

from __future__ import annotations

from dataclasses import dataclass

from tubeforge.domain.states import ApprovalGate, JobState


class InvalidTransitionError(ValueError):
    """Raised when a requested state change violates pipeline policy."""


@dataclass(frozen=True, slots=True)
class PipelineSnapshot:
    """Minimal persisted state needed to resume a failed pipeline stage safely."""

    state: JobState
    resume_state: JobState | None = None


class PipelineStateMachine:
    """Validate transitions without depending on persistence, web, or providers."""

    _NORMAL_TRANSITIONS: dict[JobState, JobState] = {
        JobState.TOPIC_CREATED: JobState.CONTENT_GENERATING,
        JobState.CONTENT_GENERATING: JobState.CONTENT_READY,
        JobState.CONTENT_READY: JobState.SCRIPT_APPROVAL_REQUIRED,
        JobState.SCRIPT_APPROVAL_REQUIRED: JobState.ASSET_ACQUISITION,
        JobState.ASSET_ACQUISITION: JobState.ASSETS_READY,
        JobState.ASSETS_READY: JobState.VOICE_GENERATION,
        JobState.VOICE_GENERATION: JobState.CAPTION_GENERATION,
        # Voice readiness is only durable after narration and both caption formats validate.
        JobState.CAPTION_GENERATION: JobState.VOICE_READY,
        JobState.VOICE_READY: JobState.PREVIEW_RENDERING,
        JobState.PREVIEW_RENDERING: JobState.PREVIEW_READY,
        JobState.PREVIEW_READY: JobState.PREVIEW_APPROVED,
        JobState.PREVIEW_APPROVED: JobState.FINAL_RENDERING,
        JobState.FINAL_RENDERING: JobState.FINAL_READY,
    }
    _APPROVAL_REQUIREMENTS: dict[JobState, ApprovalGate] = {
        JobState.ASSET_ACQUISITION: ApprovalGate.SCRIPT,
        JobState.PREVIEW_APPROVED: ApprovalGate.PREVIEW,
    }
    _FAILURE_STATES = frozenset(
        {JobState.FAILED_RETRYABLE, JobState.FAILED_VALIDATION, JobState.AUTH_REQUIRED}
    )
    _TERMINAL_STATES = frozenset({
        JobState.FINAL_READY, JobState.PUBLISHED, JobState.CANCELLED,
        JobState.FAILED_EXHAUSTED,
    })
    _PREVIEW_INVALIDATION_STATES = frozenset({
        JobState.PREVIEW_READY, JobState.PREVIEW_APPROVED, JobState.FINAL_RENDERING,
    })

    def transition(
        self,
        snapshot: PipelineSnapshot,
        target: JobState,
        *,
        approvals: frozenset[ApprovalGate] = frozenset(),
        operator_resolved: bool = False,
        authentication_restored: bool = False,
    ) -> PipelineSnapshot:
        """Return the next snapshot or reject a transition that would skip a gate."""
        current = snapshot.state
        if current in self._TERMINAL_STATES:
            raise InvalidTransitionError(f"{current.value} is terminal")
        if target is JobState.CANCELLED:
            return PipelineSnapshot(state=target)
        if target in self._FAILURE_STATES:
            if current in self._FAILURE_STATES:
                raise InvalidTransitionError("failure states cannot transition directly to another failure state")
            return PipelineSnapshot(state=target, resume_state=current)
        if current in self._FAILURE_STATES:
            return self._resume(
                snapshot, target, operator_resolved=operator_resolved,
                authentication_restored=authentication_restored,
            )
        if target is JobState.PREVIEW_RENDERING and current in self._PREVIEW_INVALIDATION_STATES:
            return PipelineSnapshot(state=target)
        expected = self._NORMAL_TRANSITIONS.get(current)
        if target is not expected:
            raise InvalidTransitionError(f"cannot transition from {current.value} to {target.value}")
        required_approval = self._APPROVAL_REQUIREMENTS.get(target)
        if required_approval is not None and required_approval not in approvals:
            raise InvalidTransitionError(f"{target.value} requires {required_approval.value} approval")
        return PipelineSnapshot(state=target)

    def _resume(
        self,
        snapshot: PipelineSnapshot,
        target: JobState,
        *,
        operator_resolved: bool,
        authentication_restored: bool,
    ) -> PipelineSnapshot:
        if snapshot.resume_state is None or target is not snapshot.resume_state:
            raise InvalidTransitionError("failed jobs may resume only at their recorded failed stage")
        if snapshot.state is JobState.FAILED_VALIDATION and not operator_resolved:
            raise InvalidTransitionError("validation failures require operator resolution")
        if snapshot.state is JobState.AUTH_REQUIRED and not authentication_restored:
            raise InvalidTransitionError("authentication must be restored before resuming")
        return PipelineSnapshot(state=target)
