"""Ensure one effective decision per reviewed approval identity."""
from alembic import op
import sqlalchemy as sa

revision = "20260810_0007"
down_revision = "20260804_0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("approvals") as batch:
        # A nullable reviewed_identity is retained for M9/M10 compatibility,
        # but SQL unique constraints permit duplicate NULLs.  The normalized
        # key makes an unbound legacy decision just as unique as a bound one.
        batch.add_column(sa.Column("decision_identity", sa.String(length=64), nullable=False, server_default=""))
        batch.create_unique_constraint("uq_approvals_decision", ["job_id", "gate", "decision_identity"])


def downgrade() -> None:
    with op.batch_alter_table("approvals") as batch:
        batch.drop_constraint("uq_approvals_decision", type_="unique")
        batch.drop_column("decision_identity")
