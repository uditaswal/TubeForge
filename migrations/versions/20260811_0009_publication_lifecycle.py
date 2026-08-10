"""Add durable M14 publication reconciliation observations."""
from alembic import op
import sqlalchemy as sa

revision = "20260811_0009"
down_revision = "20260810_0008"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.create_table("publication_observations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("publication_identity", sa.String(64), nullable=False),
        sa.Column("health", sa.String(32), nullable=False),
        sa.Column("snapshot_json", sa.Text(), nullable=False),
        sa.Column("drift_json", sa.Text(), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_publication_observations_publication_identity", "publication_observations", ["publication_identity"])

def downgrade() -> None:
    op.drop_index("ix_publication_observations_publication_identity", table_name="publication_observations")
    op.drop_table("publication_observations")
