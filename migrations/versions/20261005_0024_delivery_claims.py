"""Fenced destination claims and auditable delivery attempts.

Revision ID: 20261005_0024
Revises: 20261005_0023
"""
from alembic import op
import sqlalchemy as sa

revision = "20261005_0024"
down_revision = "20261005_0023"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("destination_deliveries") as batch:
        batch.add_column(sa.Column("claim_owner", sa.String(128)))
        batch.add_column(sa.Column("claim_token", sa.String(64)))
        batch.add_column(sa.Column("lease_expires_at", sa.DateTime(timezone=True)))
        batch.add_column(sa.Column("next_retry_at", sa.DateTime(timezone=True)))
        batch.create_index("ix_destination_deliveries_lease_expires_at", ["lease_expires_at"])
        batch.create_index("ix_destination_deliveries_next_retry_at", ["next_retry_at"])
    op.create_table(
        "delivery_attempts",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("delivery_id", sa.String(64), nullable=False),
        sa.Column("claim_token", sa.String(64), nullable=False, unique=True),
        sa.Column("kind", sa.String(24), nullable=False),
        sa.Column("state", sa.String(32), nullable=False),
        sa.Column("remote_session_id", sa.Text()),
        sa.Column("remote_id", sa.String(500)),
        sa.Column("error_message", sa.Text()),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_delivery_attempts_delivery_id", "delivery_attempts", ["delivery_id"])


def downgrade() -> None:
    op.drop_index("ix_delivery_attempts_delivery_id", table_name="delivery_attempts")
    op.drop_table("delivery_attempts")
    with op.batch_alter_table("destination_deliveries") as batch:
        batch.drop_index("ix_destination_deliveries_next_retry_at")
        batch.drop_index("ix_destination_deliveries_lease_expires_at")
        batch.drop_column("next_retry_at")
        batch.drop_column("lease_expires_at")
        batch.drop_column("claim_token")
        batch.drop_column("claim_owner")
