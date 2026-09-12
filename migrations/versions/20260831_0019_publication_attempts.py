"""Add generic multi-account publication attempt receipts."""
from alembic import op
import sqlalchemy as sa

revision = "20260831_0019"
down_revision = "20260831_0018"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.create_table("publication_attempts", sa.Column("id", sa.String(64), primary_key=True), sa.Column("job_id", sa.String(64), nullable=False), sa.Column("account_id", sa.String(64), nullable=False), sa.Column("platform", sa.String(32), nullable=False), sa.Column("idempotency_key", sa.String(200), nullable=False), sa.Column("state", sa.String(32), nullable=False), sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"), sa.Column("remote_id", sa.String(500)), sa.Column("remote_url", sa.Text()), sa.Column("error_message", sa.Text()), sa.Column("retry_eligible", sa.Boolean(), nullable=False, server_default=sa.false()), sa.Column("metadata_json", sa.Text(), nullable=False), sa.Column("started_at", sa.DateTime(timezone=True)), sa.Column("finished_at", sa.DateTime(timezone=True)), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False), sa.UniqueConstraint("idempotency_key", name="uq_publication_attempts_key"))
    op.create_index("ix_publication_attempts_job_id", "publication_attempts", ["job_id"]); op.create_index("ix_publication_attempts_account_id", "publication_attempts", ["account_id"])

def downgrade() -> None:
    op.drop_index("ix_publication_attempts_account_id", table_name="publication_attempts"); op.drop_index("ix_publication_attempts_job_id", table_name="publication_attempts"); op.drop_table("publication_attempts")
