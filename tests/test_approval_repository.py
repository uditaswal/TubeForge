from __future__ import annotations

import pytest
from sqlalchemy.exc import IntegrityError

from tubeforge.core.config import DatabaseConfig
from tubeforge.db.models import ApprovalRecord, Base
from tubeforge.db.repositories import ApprovalRepository
from tubeforge.db.session import create_database
from tubeforge.domain.states import ApprovalGate, ApprovalStatus


@pytest.fixture
def approvals(tmp_path):
    database = create_database(DatabaseConfig(url=f"sqlite:///{tmp_path / 'approvals.db'}"))
    Base.metadata.create_all(database.engine)
    try:
        yield ApprovalRepository(database.session_factory), database
    finally:
        database.dispose()


@pytest.mark.parametrize("status", [ApprovalStatus.APPROVED, ApprovalStatus.REJECTED])
def test_one_effective_decision_is_idempotent(approvals, status: ApprovalStatus) -> None:
    repository, _ = approvals
    repository.record("first", "job", ApprovalGate.PREVIEW, status, reviewed_identity="preview-1")
    repository.record("duplicate", "job", ApprovalGate.PREVIEW, status, reviewed_identity="preview-1")
    decision = repository.decision("job", ApprovalGate.PREVIEW, reviewed_identity="preview-1")
    assert decision is not None and decision.id == "first" and decision.status == status.value


def test_conflicting_decision_is_rejected_and_never_observable(approvals) -> None:
    repository, _ = approvals
    repository.record("approved", "job", ApprovalGate.PREVIEW, ApprovalStatus.APPROVED, reviewed_identity="preview-1")
    with pytest.raises(ValueError, match="conflicts"):
        repository.record("rejected", "job", ApprovalGate.PREVIEW, ApprovalStatus.REJECTED, reviewed_identity="preview-1")
    assert repository.approved("job", ApprovalGate.PREVIEW, reviewed_identity="preview-1") is not None
    assert repository.rejected("job", ApprovalGate.PREVIEW, reviewed_identity="preview-1") is None


def test_database_constraint_also_covers_legacy_null_identity(approvals) -> None:
    _, database = approvals
    with pytest.raises(IntegrityError):
        with database.session_factory.begin() as session:
            session.add_all((
                ApprovalRecord(id="one", job_id="job", gate="script", status="approved", created_at=__import__("datetime").datetime.now(__import__("datetime").UTC), reviewed_identity=None, decision_identity=""),
                ApprovalRecord(id="two", job_id="job", gate="script", status="rejected", created_at=__import__("datetime").datetime.now(__import__("datetime").UTC), reviewed_identity=None, decision_identity=""),
            ))
