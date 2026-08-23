"""Add M15/M16 read-only analytics, evaluations, and proposals."""
from alembic import op
import sqlalchemy as sa

revision = "20260811_0010"
down_revision = "20260811_0009"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.create_table("analytics_snapshots", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("publication_identity", sa.String(64), nullable=False), sa.Column("remote_video_id", sa.String(200), nullable=False), sa.Column("channel_id", sa.String(200), nullable=False), sa.Column("snapshot_identity", sa.String(64), nullable=False), sa.Column("report_start", sa.DateTime(timezone=True), nullable=False), sa.Column("report_end", sa.DateTime(timezone=True), nullable=False), sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False), sa.Column("status", sa.String(32), nullable=False), sa.Column("views", sa.Integer()), sa.Column("impressions", sa.Integer()), sa.Column("metrics_json", sa.Text(), nullable=False), sa.Column("provenance_json", sa.Text(), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.UniqueConstraint("snapshot_identity", name="uq_analytics_snapshots_identity"))
    op.create_index("ix_analytics_snapshots_publication_identity", "analytics_snapshots", ["publication_identity"])
    op.create_table("performance_evaluations", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("publication_identity", sa.String(64), nullable=False), sa.Column("evaluation_identity", sa.String(64), nullable=False), sa.Column("snapshot_identities_json", sa.Text(), nullable=False), sa.Column("evaluator_version", sa.String(100), nullable=False), sa.Column("dimensions_json", sa.Text(), nullable=False), sa.Column("derived_metrics_json", sa.Text(), nullable=False), sa.Column("recommendations_json", sa.Text(), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.UniqueConstraint("evaluation_identity", name="uq_performance_evaluations_identity"))
    op.create_index("ix_performance_evaluations_publication_identity", "performance_evaluations", ["publication_identity"])
    op.create_table("optimization_proposals", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("publication_identity", sa.String(64), nullable=False), sa.Column("remote_video_id", sa.String(200), nullable=False), sa.Column("evaluation_identity", sa.String(64), nullable=False), sa.Column("snapshot_identity", sa.String(64), nullable=False), sa.Column("proposal_identity", sa.String(64), nullable=False), sa.Column("proposal_type", sa.String(32), nullable=False), sa.Column("status", sa.String(32), nullable=False), sa.Column("rationale_json", sa.Text(), nullable=False), sa.Column("proposal_version", sa.String(100), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.UniqueConstraint("proposal_identity", name="uq_optimization_proposals_identity"))
    op.create_index("ix_optimization_proposals_publication_identity", "optimization_proposals", ["publication_identity"])

def downgrade() -> None:
    op.drop_index("ix_optimization_proposals_publication_identity", table_name="optimization_proposals"); op.drop_table("optimization_proposals")
    op.drop_index("ix_performance_evaluations_publication_identity", table_name="performance_evaluations"); op.drop_table("performance_evaluations")
    op.drop_index("ix_analytics_snapshots_publication_identity", table_name="analytics_snapshots"); op.drop_table("analytics_snapshots")
