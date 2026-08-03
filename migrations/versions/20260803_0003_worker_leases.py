"""Add M5 worker leases, retry metadata, and external operation receipts.

Revision ID: 20260803_0003
Revises: 20260803_0002
"""

from alembic import op
import sqlalchemy as sa

revision = "20260803_0003"
down_revision = "20260803_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("pipeline_jobs") as batch:
        batch.add_column(sa.Column("claim_owner", sa.String(length=128)))
        batch.add_column(sa.Column("claimed_at", sa.DateTime(timezone=True)))
        batch.add_column(sa.Column("lease_expires_at", sa.DateTime(timezone=True)))
        batch.add_column(sa.Column("heartbeat_at", sa.DateTime(timezone=True)))
        batch.add_column(sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"))
        batch.add_column(sa.Column("next_retry_at", sa.DateTime(timezone=True)))
        batch.add_column(sa.Column("cancellation_requested_at", sa.DateTime(timezone=True)))
        batch.add_column(sa.Column("authentication_restored_at", sa.DateTime(timezone=True)))
    op.create_index("ix_pipeline_jobs_lease_expires_at", "pipeline_jobs", ["lease_expires_at"])
    op.create_index("ix_pipeline_jobs_next_retry_at", "pipeline_jobs", ["next_retry_at"])
    op.create_table("external_operations", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("job_id", sa.String(length=64), nullable=False), sa.Column("operation", sa.String(length=64), nullable=False), sa.Column("idempotency_key", sa.String(length=200), nullable=False), sa.Column("receipt_json", sa.Text()), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.Column("completed_at", sa.DateTime(timezone=True)), sa.UniqueConstraint("idempotency_key", name="uq_external_operations_idempotency_key"))
    op.create_index("ix_external_operations_job_id", "external_operations", ["job_id"])


def downgrade() -> None:
    op.drop_index("ix_external_operations_job_id", table_name="external_operations")
    op.drop_table("external_operations")
    op.drop_index("ix_pipeline_jobs_next_retry_at", table_name="pipeline_jobs")
    op.drop_index("ix_pipeline_jobs_lease_expires_at", table_name="pipeline_jobs")
    with op.batch_alter_table("pipeline_jobs") as batch:
        batch.drop_column("authentication_restored_at"); batch.drop_column("cancellation_requested_at")
        batch.drop_column("next_retry_at"); batch.drop_column("attempt_count"); batch.drop_column("heartbeat_at")
        batch.drop_column("lease_expires_at"); batch.drop_column("claimed_at"); batch.drop_column("claim_owner")
