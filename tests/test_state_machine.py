from __future__ import annotations

import pytest

from tubeforge.core.state_machine import (
    InvalidTransitionError,
    PipelineSnapshot,
    PipelineStateMachine,
)
from tubeforge.domain.states import ApprovalGate, JobState


def test_valid_phase_one_workflow_requires_each_approval() -> None:
    machine = PipelineStateMachine()
    snapshot = PipelineSnapshot(JobState.TOPIC_CREATED)
    for target in (
        JobState.CONTENT_GENERATING,
        JobState.CONTENT_READY,
        JobState.SCRIPT_APPROVAL_REQUIRED,
    ):
        snapshot = machine.transition(snapshot, target)
    snapshot = machine.transition(snapshot, JobState.ASSET_ACQUISITION, approvals=frozenset({ApprovalGate.SCRIPT}))
    for target in (
        JobState.VOICE_GENERATION,
        JobState.CAPTION_GENERATION,
        JobState.PREVIEW_RENDERING,
        JobState.PREVIEW_APPROVAL_REQUIRED,
    ):
        snapshot = machine.transition(snapshot, target)
    snapshot = machine.transition(snapshot, JobState.FINAL_RENDERING, approvals=frozenset({ApprovalGate.PREVIEW}))
    for target in (
        JobState.PRIVATE_UPLOAD_READY,
        JobState.PRIVATE_UPLOADING,
        JobState.PUBLISH_APPROVAL_REQUIRED,
    ):
        snapshot = machine.transition(snapshot, target)
    snapshot = machine.transition(snapshot, JobState.PUBLISHED, approvals=frozenset({ApprovalGate.PUBLIC_PUBLISH}))

    assert snapshot.state is JobState.PUBLISHED


def test_invalid_transition_cannot_skip_required_approval() -> None:
    machine = PipelineStateMachine()
    with pytest.raises(InvalidTransitionError, match="cannot transition"):
        machine.transition(PipelineSnapshot(JobState.CONTENT_READY), JobState.ASSET_ACQUISITION)
    with pytest.raises(InvalidTransitionError, match="script approval"):
        machine.transition(PipelineSnapshot(JobState.SCRIPT_APPROVAL_REQUIRED), JobState.ASSET_ACQUISITION)
    with pytest.raises(InvalidTransitionError, match="public_publish approval"):
        machine.transition(PipelineSnapshot(JobState.PUBLISH_APPROVAL_REQUIRED), JobState.PUBLISHED)


def test_terminal_states_cannot_transition() -> None:
    machine = PipelineStateMachine()
    for terminal in (JobState.PUBLISHED, JobState.CANCELLED):
        with pytest.raises(InvalidTransitionError, match="terminal"):
            machine.transition(PipelineSnapshot(terminal), JobState.CONTENT_GENERATING)


def test_retryable_failure_resumes_only_failed_stage() -> None:
    machine = PipelineStateMachine()
    failed = machine.transition(PipelineSnapshot(JobState.VOICE_GENERATION), JobState.FAILED_RETRYABLE)
    assert failed.resume_state is JobState.VOICE_GENERATION
    with pytest.raises(InvalidTransitionError, match="recorded failed stage"):
        machine.transition(failed, JobState.CAPTION_GENERATION)

    resumed = machine.transition(failed, JobState.VOICE_GENERATION)
    assert resumed == PipelineSnapshot(JobState.VOICE_GENERATION)


def test_validation_and_auth_failures_require_recovery_actions() -> None:
    machine = PipelineStateMachine()
    validation_failed = machine.transition(PipelineSnapshot(JobState.CONTENT_GENERATING), JobState.FAILED_VALIDATION)
    with pytest.raises(InvalidTransitionError, match="operator resolution"):
        machine.transition(validation_failed, JobState.CONTENT_GENERATING)
    assert machine.transition(validation_failed, JobState.CONTENT_GENERATING, operator_resolved=True).state is JobState.CONTENT_GENERATING

    auth_failed = machine.transition(PipelineSnapshot(JobState.PRIVATE_UPLOADING), JobState.AUTH_REQUIRED)
    with pytest.raises(InvalidTransitionError, match="authentication"):
        machine.transition(auth_failed, JobState.PRIVATE_UPLOADING)
    assert machine.transition(auth_failed, JobState.PRIVATE_UPLOADING, authentication_restored=True).state is JobState.PRIVATE_UPLOADING
