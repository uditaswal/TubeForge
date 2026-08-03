"""Initialize TubeForge schema version tracking.

Revision ID: 20260803_0001
Revises:
Create Date: 2026-08-03 00:00:00
"""

# revision identifiers, used by Alembic.
revision = "20260803_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Establish the initial migration baseline; domain tables arrive later."""


def downgrade() -> None:
    """The baseline has no application tables to remove."""
