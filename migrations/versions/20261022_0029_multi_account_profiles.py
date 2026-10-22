"""Local account profiles and per-job destination intent."""
from alembic import op
import sqlalchemy as sa

revision = "20261022_0029"
down_revision = "20261005_0028"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("social_accounts") as batch:
        batch.add_column(sa.Column("category", sa.String(100), nullable=False, server_default="general"))
        batch.add_column(sa.Column("default_description", sa.Text(), nullable=False, server_default=""))
    with op.batch_alter_table("pipeline_jobs") as batch:
        batch.add_column(sa.Column("video_description", sa.Text()))
    op.create_table("video_destination_intents",
        sa.Column("job_id", sa.String(64), primary_key=True),
        sa.Column("account_id", sa.String(64), primary_key=True),
        sa.Column("platform", sa.String(32), nullable=False),
        sa.Column("account_name", sa.String(200), nullable=False),
        sa.Column("category", sa.String(100), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("video_destination_intents")
    with op.batch_alter_table("pipeline_jobs") as batch:
        batch.drop_column("video_description")
    with op.batch_alter_table("social_accounts") as batch:
        batch.drop_column("default_description")
        batch.drop_column("category")
