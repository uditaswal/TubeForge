"""Add durable topic backlog and scheduler execution fences."""

from alembic import op
import sqlalchemy as sa

revision = "20260831_0016"
down_revision = "20260831_0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table("topics", sa.Column("id", sa.String(64), primary_key=True), sa.Column("title", sa.String(500), nullable=False), sa.Column("notes", sa.Text(), nullable=False, server_default=""), sa.Column("priority", sa.Integer(), nullable=False, server_default="0"), sa.Column("status", sa.String(32), nullable=False, server_default="ready"), sa.Column("options_json", sa.Text(), nullable=False, server_default="{}"), sa.Column("generation_job_id", sa.String(64)), sa.Column("reserved_by", sa.String(128)), sa.Column("reserved_at", sa.DateTime(timezone=True)), sa.Column("lease_expires_at", sa.DateTime(timezone=True)), sa.Column("failure_message", sa.Text()), sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_topics_status", "topics", ["status"]); op.create_index("ix_topics_priority", "topics", ["priority"]); op.create_index("ix_topics_generation_job_id", "topics", ["generation_job_id"]); op.create_index("ix_topics_lease_expires_at", "topics", ["lease_expires_at"])
    op.create_table("schedules", sa.Column("id", sa.String(64), primary_key=True), sa.Column("name", sa.String(200), nullable=False, unique=True), sa.Column("cron", sa.String(120), nullable=False), sa.Column("timezone", sa.String(100), nullable=False, server_default="UTC"), sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()), sa.Column("options_json", sa.Text(), nullable=False, server_default="{}"), sa.Column("last_run_at", sa.DateTime(timezone=True)), sa.Column("next_run_at", sa.DateTime(timezone=True)), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_schedules_next_run_at", "schedules", ["next_run_at"])
    op.create_table("schedule_runs", sa.Column("id", sa.String(64), primary_key=True), sa.Column("schedule_id", sa.String(64), nullable=False), sa.Column("run_key", sa.String(120), nullable=False), sa.Column("state", sa.String(32), nullable=False), sa.Column("topic_id", sa.String(64)), sa.Column("job_id", sa.String(64)), sa.Column("details_json", sa.Text(), nullable=False, server_default="{}"), sa.Column("started_at", sa.DateTime(timezone=True), nullable=False), sa.Column("finished_at", sa.DateTime(timezone=True)), sa.UniqueConstraint("schedule_id", "run_key", name="uq_schedule_runs_schedule_key"))
    op.create_index("ix_schedule_runs_schedule_id", "schedule_runs", ["schedule_id"]); op.create_index("ix_schedule_runs_topic_id", "schedule_runs", ["topic_id"]); op.create_index("ix_schedule_runs_job_id", "schedule_runs", ["job_id"])


def downgrade() -> None:
    op.drop_table("schedule_runs"); op.drop_index("ix_schedules_next_run_at", table_name="schedules"); op.drop_table("schedules")
    for name in ("ix_topics_lease_expires_at", "ix_topics_generation_job_id", "ix_topics_priority", "ix_topics_status"): op.drop_index(name, table_name="topics")
    op.drop_table("topics")
