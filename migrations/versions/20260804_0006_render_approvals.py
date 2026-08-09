"""Add immutable preview approval binding metadata."""
from alembic import op
import sqlalchemy as sa

revision = "20260804_0006"
down_revision = "20260803_0005"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.add_column("approvals", sa.Column("actor", sa.String(length=200), nullable=True))
    op.add_column("approvals", sa.Column("reviewed_identity", sa.String(length=64), nullable=True))
    op.add_column("approvals", sa.Column("audit_json", sa.Text(), nullable=True))
    op.create_index("ix_approvals_reviewed_identity", "approvals", ["reviewed_identity"])

def downgrade() -> None:
    op.drop_index("ix_approvals_reviewed_identity", table_name="approvals")
    op.drop_column("approvals", "audit_json")
    op.drop_column("approvals", "reviewed_identity")
    op.drop_column("approvals", "actor")
