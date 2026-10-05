"""Persist the bounded host-Codex invocation allowance.

Revision ID: 20260927_0020
Revises: 20260831_0019
"""

from alembic import op
import sqlalchemy as sa

revision = "20260927_0020"
down_revision = "20260831_0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("generation_cache", sa.Column("invocation_count", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("generation_cache", sa.Column("failure_json", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("generation_cache", "failure_json")
    op.drop_column("generation_cache", "invocation_count")
