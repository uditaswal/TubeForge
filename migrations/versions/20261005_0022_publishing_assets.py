"""Canonical content-addressed assets for shared publishing selection.

Revision ID: 20261005_0022
Revises: 20261005_0021
"""

from alembic import op
import sqlalchemy as sa

revision = "20261005_0022"
down_revision = "20261005_0021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "publishing_assets",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("staged_path", sa.Text(), nullable=False),
        sa.Column("source_job_id", sa.String(64)),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("duration_seconds", sa.Float(), nullable=False),
        sa.Column("width", sa.Integer(), nullable=False),
        sa.Column("height", sa.Integer(), nullable=False),
        sa.Column("state", sa.String(32), nullable=False, server_default="ready"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("sha256", name="uq_publishing_assets_sha256"),
    )
    op.create_index("ix_publishing_assets_source_job_id", "publishing_assets", ["source_job_id"])


def downgrade() -> None:
    op.drop_index("ix_publishing_assets_source_job_id", table_name="publishing_assets")
    op.drop_table("publishing_assets")
