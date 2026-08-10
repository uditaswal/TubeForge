"""Add durable non-secret M13 publication records."""
from alembic import op
import sqlalchemy as sa

revision = "20260810_0008"
down_revision = "20260810_0007"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.create_table("publications", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("job_id", sa.String(64), nullable=False), sa.Column("publication_identity", sa.String(64), nullable=False), sa.Column("package_identity", sa.String(64), nullable=False), sa.Column("channel_id", sa.String(200), nullable=False), sa.Column("state", sa.String(32), nullable=False), sa.Column("remote_video_id", sa.String(200)), sa.Column("metadata_applied", sa.Boolean(), nullable=False), sa.Column("thumbnail_applied", sa.Boolean(), nullable=False), sa.Column("provenance_json", sa.Text(), nullable=False), sa.Column("error_message", sa.Text()), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False), sa.UniqueConstraint("publication_identity", name="uq_publications_identity"))
    op.create_index("ix_publications_job_id", "publications", ["job_id"])
def downgrade() -> None:
    op.drop_index("ix_publications_job_id", table_name="publications")
    op.drop_table("publications")
