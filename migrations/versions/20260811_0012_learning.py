"""Add M20--M23 experiment learning and reviewable brief records."""
from alembic import op
import sqlalchemy as sa

revision = "20260811_0012"
down_revision = "20260811_0011"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.create_table("experiment_outcomes", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("execution_identity", sa.String(64), nullable=False), sa.Column("outcome_identity", sa.String(64), nullable=False), sa.Column("evaluator_version", sa.String(100), nullable=False), sa.Column("outcome", sa.String(32), nullable=False), sa.Column("baseline_snapshot_identity", sa.String(64)), sa.Column("post_snapshot_identities_json", sa.Text(), nullable=False), sa.Column("evidence_json", sa.Text(), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.UniqueConstraint("outcome_identity", name="uq_experiment_outcomes_identity"))
    op.create_table("learning_events", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("event_identity", sa.String(64), nullable=False), sa.Column("outcome_identity", sa.String(64), nullable=False), sa.Column("channel_id", sa.String(200), nullable=False), sa.Column("event_type", sa.String(64), nullable=False), sa.Column("payload_json", sa.Text(), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.UniqueConstraint("event_identity", name="uq_learning_events_identity"))
    op.create_table("channel_baselines", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("channel_id", sa.String(200), nullable=False), sa.Column("baseline_identity", sa.String(64), nullable=False), sa.Column("baseline_version", sa.String(100), nullable=False), sa.Column("sample_size", sa.Integer(), nullable=False), sa.Column("statistics_json", sa.Text(), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.UniqueConstraint("baseline_identity", name="uq_channel_baselines_identity"))
    op.create_table("next_video_recommendations", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("channel_id", sa.String(200), nullable=False), sa.Column("recommendation_identity", sa.String(64), nullable=False), sa.Column("recommendation_version", sa.String(100), nullable=False), sa.Column("status", sa.String(32), nullable=False), sa.Column("recommendation_type", sa.String(64), nullable=False), sa.Column("confidence", sa.String(16), nullable=False), sa.Column("evidence_json", sa.Text(), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.UniqueConstraint("recommendation_identity", name="uq_next_video_recommendations_identity"))
    op.create_table("next_video_briefs", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("channel_id", sa.String(200), nullable=False), sa.Column("brief_identity", sa.String(64), nullable=False), sa.Column("template_version", sa.String(100), nullable=False), sa.Column("status", sa.String(32), nullable=False), sa.Column("recommendation_identities_json", sa.Text(), nullable=False), sa.Column("content_json", sa.Text(), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.UniqueConstraint("brief_identity", name="uq_next_video_briefs_identity"))

def downgrade() -> None:
    op.drop_table("next_video_briefs"); op.drop_table("next_video_recommendations"); op.drop_table("channel_baselines"); op.drop_table("learning_events"); op.drop_table("experiment_outcomes")
