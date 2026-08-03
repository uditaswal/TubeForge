"""Persist M4 pipeline jobs, approvals, and checkpoint artifacts.

Revision ID: 20260803_0002
Revises: 20260803_0001
Create Date: 2026-08-03 00:10:00
"""

from alembic import op
import sqlalchemy as sa


revision = "20260803_0002"
down_revision = "20260803_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table("pipeline_jobs", sa.Column("id", sa.String(length=64), primary_key=True), sa.Column("request_json", sa.Text(), nullable=False), sa.Column("state", sa.String(length=64), nullable=False), sa.Column("resume_state", sa.String(length=64)), sa.Column("failure_message", sa.Text()), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False))
    op.create_table("artifacts", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("job_id", sa.String(length=64), nullable=False), sa.Column("stage", sa.String(length=64), nullable=False), sa.Column("name", sa.String(length=120), nullable=False), sa.Column("path", sa.Text(), nullable=False), sa.Column("checksum_sha256", sa.String(length=64), nullable=False), sa.Column("provenance_json", sa.Text(), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_artifacts_job_id", "artifacts", ["job_id"])
    op.create_table("approvals", sa.Column("id", sa.String(length=100), primary_key=True), sa.Column("job_id", sa.String(length=64), nullable=False), sa.Column("gate", sa.String(length=64), nullable=False), sa.Column("status", sa.String(length=32), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_approvals_job_id", "approvals", ["job_id"])


def downgrade() -> None:
    op.drop_index("ix_approvals_job_id", table_name="approvals")
    op.drop_table("approvals")
    op.drop_index("ix_artifacts_job_id", table_name="artifacts")
    op.drop_table("artifacts")
    op.drop_table("pipeline_jobs")
