"""Operator-facing progression chip for a batch short; pure so the page and API tests share it."""

STAGES = ('imported', 'scripting', 'rendering', 'needs_review', 'approved', 'ready')
STAGE_LABELS = {'imported': 'Imported', 'scripting': 'Scripting', 'rendering': 'Rendering', 'needs_review': 'Needs review',
                'approved': 'Approved', 'ready': 'Ready', 'attention': 'Needs attention'}
_SCRIPTING = {'topic_created', 'source_inspecting', 'source_acquiring', 'source_analyzing', 'clip_rendering', 'content_generating', 'content_ready'}
_ATTENTION = {'failed_retryable', 'failed_validation', 'auth_required', 'failed_exhausted', 'cancelled', 'needs operator decision'}
# Waiting on a person in Generations (script or preview approval) counts as review work.
_WAITING = {'script_approval_required', 'preview_ready', 'preview_approval_required'}


def stage_for(job_state: str | None, review_state: str | None) -> str:
    """Map a job state plus the saved Day review state to one chip; failures never read as progress."""
    if not job_state:
        return 'imported'
    if job_state in _ATTENTION:
        return 'attention'
    if job_state in _SCRIPTING:
        return 'scripting'
    if job_state in _WAITING:
        return 'needs_review'
    if job_state == 'final_ready' or job_state.startswith('publication') or job_state in {'private_upload_ready', 'published'}:
        return review_state if review_state in {'approved', 'ready'} else 'needs_review'
    return 'rendering'
