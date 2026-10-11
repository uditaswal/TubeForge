"""Manual and scheduled publish jobs with durable destination identities.

Revision ID: 20261005_0023
Revises: 20261005_0022
"""

from alembic import op
import sqlalchemy as sa

revision = "20261005_0023"
down_revision = "20261005_0022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "publish_jobs",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("asset_id", sa.String(64), nullable=False),
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column("edition", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("state", sa.String(32), nullable=False),
        sa.Column("metadata_json", sa.Text(), nullable=False),
        sa.Column("scheduled_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_publish_jobs_asset_id", "publish_jobs", ["asset_id"])
    op.create_table(
        "destination_deliveries",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("publish_job_id", sa.String(64), nullable=False),
        sa.Column("asset_id", sa.String(64), nullable=False),
        sa.Column("account_id", sa.String(64), nullable=False),
        sa.Column("platform", sa.String(32), nullable=False),
        sa.Column("external_account_id", sa.String(300), nullable=False),
        sa.Column("edition", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("state", sa.String(32), nullable=False),
        sa.Column("required", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("metadata_json", sa.Text(), nullable=False),
        sa.Column("remote_id", sa.String(500)),
        sa.Column("remote_url", sa.Text()),
        sa.Column("remote_session_id", sa.Text()),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_message", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("asset_id", "account_id", "edition", name="uq_destination_delivery_identity"),
    )
    op.create_index("ix_destination_deliveries_publish_job_id", "destination_deliveries", ["publish_job_id"])
    op.create_index("ix_destination_deliveries_account_id", "destination_deliveries", ["account_id"])


def downgrade() -> None:
    op.drop_index("ix_destination_deliveries_account_id", table_name="destination_deliveries")
    op.drop_index("ix_destination_deliveries_publish_job_id", table_name="destination_deliveries")
    op.drop_table("destination_deliveries")
    op.drop_index("ix_publish_jobs_asset_id", table_name="publish_jobs")
    op.drop_table("publish_jobs")
