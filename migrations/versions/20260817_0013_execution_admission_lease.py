"""Add a database-backed global admission lease for heavy worker execution."""

from alembic import op
import sqlalchemy as sa

revision = "20260817_0013"
down_revision = "20260811_0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "heavy_work_leases",
        sa.Column("name", sa.String(length=64), primary_key=True),
        sa.Column("owner", sa.String(length=128)),
        sa.Column("acquired_at", sa.DateTime(timezone=True)),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True)),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_heavy_work_leases_lease_expires_at", "heavy_work_leases", ["lease_expires_at"])


def downgrade() -> None:
    op.drop_index("ix_heavy_work_leases_lease_expires_at", table_name="heavy_work_leases")
    op.drop_table("heavy_work_leases")
