"""Add local administrator and opaque dashboard sessions."""
from alembic import op
import sqlalchemy as sa

revision = "20260831_0017"
down_revision = "20260831_0016"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.create_table("admin_users", sa.Column("id", sa.String(64), primary_key=True), sa.Column("username", sa.String(100), nullable=False, unique=True), sa.Column("password_hash", sa.Text(), nullable=False), sa.Column("disabled", sa.Boolean(), nullable=False, server_default=sa.false()), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False))
    op.create_table("auth_sessions", sa.Column("id", sa.String(64), primary_key=True), sa.Column("user_id", sa.String(64), nullable=False), sa.Column("token_hash", sa.String(64), nullable=False, unique=True), sa.Column("csrf_token", sa.String(128), nullable=False), sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_auth_sessions_user_id", "auth_sessions", ["user_id"]); op.create_index("ix_auth_sessions_expires_at", "auth_sessions", ["expires_at"])

def downgrade() -> None:
    op.drop_index("ix_auth_sessions_expires_at", table_name="auth_sessions"); op.drop_index("ix_auth_sessions_user_id", table_name="auth_sessions"); op.drop_table("auth_sessions"); op.drop_table("admin_users")
