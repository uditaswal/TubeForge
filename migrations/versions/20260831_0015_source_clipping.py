"""Persist source-media and future creator monitoring identities."""

from alembic import op
import sqlalchemy as sa

revision = "20260831_0015"
down_revision = "20260831_0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "source_media",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("job_id", sa.String(length=64), nullable=False),
        sa.Column("provider", sa.String(length=80), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("external_id", sa.String(length=300)),
        sa.Column("creator_id", sa.String(length=300)),
        sa.Column("title", sa.String(length=500)),
        sa.Column("duration_seconds", sa.Float()),
        sa.Column("metadata_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("job_id", name="uq_source_media_job"),
    )
    op.create_index("ix_source_media_job_id", "source_media", ["job_id"])
    op.create_index("ix_source_media_external_id", "source_media", ["external_id"])
    op.create_index("ix_source_media_creator_id", "source_media", ["creator_id"])
    op.create_table(
        "creator_sources",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("provider", sa.String(length=80), nullable=False),
        sa.Column("creator_url", sa.Text(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("check_interval_seconds", sa.Integer(), nullable=False, server_default="3600"),
        sa.Column("last_checked_at", sa.DateTime(timezone=True)),
        sa.Column("last_seen_content_id", sa.String(length=300)),
        sa.Column("metadata_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("provider", "creator_url", name="uq_creator_sources_provider_url"),
    )


def downgrade() -> None:
    op.drop_table("creator_sources")
    op.drop_index("ix_source_media_creator_id", table_name="source_media")
    op.drop_index("ix_source_media_external_id", table_name="source_media")
    op.drop_index("ix_source_media_job_id", table_name="source_media")
    op.drop_table("source_media")
