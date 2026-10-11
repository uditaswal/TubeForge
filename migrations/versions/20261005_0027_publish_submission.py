"""Exact reviewed identity and actor for manual publishing submission.

Revision ID: 20261005_0027
Revises: 20261005_0026
"""
from alembic import op
import sqlalchemy as sa

revision = "20261005_0027"
down_revision = "20261005_0026"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("publish_jobs") as batch:
        batch.add_column(sa.Column("reviewed_identity", sa.String(64)))
        batch.add_column(sa.Column("submitted_at", sa.DateTime(timezone=True)))
        batch.add_column(sa.Column("submitted_by", sa.String(64)))


def downgrade() -> None:
    with op.batch_alter_table("publish_jobs") as batch:
        batch.drop_column("submitted_by")
        batch.drop_column("submitted_at")
        batch.drop_column("reviewed_identity")
