"""Persist short-lived, single-use publishing account OAuth attempts.

Revision ID: 20261005_0021
Revises: 20260927_0020
"""

from alembic import op
import sqlalchemy as sa

revision = "20261005_0021"
down_revision = "20260927_0020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "oauth_connections",
        sa.Column("state_hash", sa.String(64), primary_key=True),
        sa.Column("platform", sa.String(32), nullable=False),
        sa.Column("account_id", sa.String(64)),
        sa.Column("session_id", sa.String(64), nullable=False),
        sa.Column("verifier_ciphertext", sa.Text()),
        sa.Column("redirect_uri", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True)),
        sa.Column("candidate_external_id", sa.String(300)),
        sa.Column("candidate_label", sa.String(200)),
        sa.Column("candidate_credential_ciphertext", sa.Text()),
        sa.Column("candidate_scopes_json", sa.Text()),
        sa.Column("candidate_token_expires_at", sa.DateTime(timezone=True)),
        sa.Column("confirmed_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_oauth_connections_expires_at", "oauth_connections", ["expires_at"])


def downgrade() -> None:
    op.drop_index("ix_oauth_connections_expires_at", table_name="oauth_connections")
    op.drop_table("oauth_connections")
