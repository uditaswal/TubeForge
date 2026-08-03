"""Add M6 persistent content-generation cache reservations.

Revision ID: 20260803_0004
Revises: 20260803_0003
"""

from alembic import op
import sqlalchemy as sa

revision = "20260803_0004"
down_revision = "20260803_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "generation_cache",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("cache_key", sa.String(length=64), nullable=False),
        sa.Column("normalized_request_json", sa.Text(), nullable=False),
        sa.Column("provider", sa.String(length=100), nullable=False),
        sa.Column("model", sa.String(length=200), nullable=False),
        sa.Column("prompt_version", sa.String(length=100), nullable=False),
        sa.Column("state", sa.String(length=16), nullable=False),
        sa.Column("reservation_token", sa.String(length=64)),
        sa.Column("reservation_expires_at", sa.DateTime(timezone=True)),
        sa.Column("package_json", sa.Text()),
        sa.Column("provenance_json", sa.Text()),
        sa.Column("usage_json", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("cache_key", name="uq_generation_cache_key"),
    )
    op.create_index("ix_generation_cache_reservation_expires_at", "generation_cache", ["reservation_expires_at"])


def downgrade() -> None:
    op.drop_index("ix_generation_cache_reservation_expires_at", table_name="generation_cache")
    op.drop_table("generation_cache")
