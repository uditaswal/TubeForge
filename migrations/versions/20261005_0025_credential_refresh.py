"""Fence account credential refresh across worker processes.

Revision ID: 20261005_0025
Revises: 20261005_0024
"""
from alembic import op
import sqlalchemy as sa

revision = "20261005_0025"
down_revision = "20261005_0024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("social_accounts") as batch:
        batch.add_column(sa.Column("credential_refresh_owner", sa.String(128)))
        batch.add_column(sa.Column("credential_refresh_fence", sa.String(64)))
        batch.add_column(sa.Column("credential_refresh_lease_expires_at", sa.DateTime(timezone=True)))


def downgrade() -> None:
    with op.batch_alter_table("social_accounts") as batch:
        batch.drop_column("credential_refresh_lease_expires_at")
        batch.drop_column("credential_refresh_fence")
        batch.drop_column("credential_refresh_owner")
