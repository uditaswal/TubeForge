"""Associate queued topics and schedules with exact local accounts."""

from alembic import op
import sqlalchemy as sa


revision = "20261022_0030"
down_revision = "20261022_0029"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("topics") as batch:
        batch.add_column(sa.Column("account_id", sa.String(64)))
        batch.create_index("ix_topics_account_id", ["account_id"])
    with op.batch_alter_table("schedules") as batch:
        batch.add_column(sa.Column("account_id", sa.String(64)))
        batch.create_index("ix_schedules_account_id", ["account_id"])


def downgrade() -> None:
    with op.batch_alter_table("schedules") as batch:
        batch.drop_index("ix_schedules_account_id")
        batch.drop_column("account_id")
    with op.batch_alter_table("topics") as batch:
        batch.drop_index("ix_topics_account_id")
        batch.drop_column("account_id")
