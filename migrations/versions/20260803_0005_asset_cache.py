"""Add M8 asset cache reservations.
Revision ID: 20260803_0005
Revises: 20260803_0004
"""
from alembic import op
import sqlalchemy as sa
revision = "20260803_0005"
down_revision = "20260803_0004"
branch_labels = None
depends_on = None
def upgrade() -> None:
    op.create_table("asset_cache", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("cache_key", sa.String(64), nullable=False), sa.Column("state", sa.String(16), nullable=False), sa.Column("reservation_token", sa.String(64)), sa.Column("reservation_expires_at", sa.DateTime(timezone=True)), sa.Column("path", sa.Text()), sa.Column("checksum_sha256", sa.String(64)), sa.Column("metadata_json", sa.Text()), sa.Column("failure_message", sa.Text()), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False), sa.Column("accepted_at", sa.DateTime(timezone=True)), sa.UniqueConstraint("cache_key", name="uq_asset_cache_key"))
    op.create_index("ix_asset_cache_reservation_expires_at", "asset_cache", ["reservation_expires_at"])
def downgrade() -> None:
    op.drop_index("ix_asset_cache_reservation_expires_at", table_name="asset_cache")
    op.drop_table("asset_cache")
