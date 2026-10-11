"""Durable operator requests for uncertain delivery reconciliation.

Revision ID: 20261005_0028
Revises: 20261005_0027
"""
from alembic import op
import sqlalchemy as sa

revision = "20261005_0028"
down_revision = "20261005_0027"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("destination_deliveries") as batch:
        batch.add_column(sa.Column("requested_action", sa.String(32)))
        batch.add_column(sa.Column("requested_by", sa.String(64)))
        batch.add_column(sa.Column("requested_at", sa.DateTime(timezone=True)))


def downgrade() -> None:
    with op.batch_alter_table("destination_deliveries") as batch:
        batch.drop_column("requested_at")
        batch.drop_column("requested_by")
        batch.drop_column("requested_action")
