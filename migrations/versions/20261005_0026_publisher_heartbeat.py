"""Publisher worker presence for truthful Studio readiness.

Revision ID: 20261005_0026
Revises: 20261005_0025
"""
from alembic import op
import sqlalchemy as sa

revision = "20261005_0026"
down_revision = "20261005_0025"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "publisher_worker_heartbeats",
        sa.Column("id", sa.String(128), primary_key=True),
        sa.Column("platforms_json", sa.Text(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_publisher_worker_heartbeats_last_seen_at", "publisher_worker_heartbeats", ["last_seen_at"])


def downgrade() -> None:
    op.drop_index("ix_publisher_worker_heartbeats_last_seen_at", table_name="publisher_worker_heartbeats")
    op.drop_table("publisher_worker_heartbeats")
