"""Add encrypted social destination account records."""
from alembic import op
import sqlalchemy as sa

revision = "20260831_0018"
down_revision = "20260831_0017"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.create_table("social_accounts", sa.Column("id", sa.String(64), primary_key=True), sa.Column("platform", sa.String(32), nullable=False), sa.Column("display_name", sa.String(200), nullable=False), sa.Column("external_account_id", sa.String(300)), sa.Column("auth_type", sa.String(32), nullable=False), sa.Column("credential_ciphertext", sa.Text()), sa.Column("scopes_json", sa.Text(), nullable=False, server_default="[]"), sa.Column("token_expires_at", sa.DateTime(timezone=True)), sa.Column("status", sa.String(32), nullable=False, server_default="unconfigured"), sa.Column("capabilities_json", sa.Text(), nullable=False, server_default="[]"), sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.false()), sa.Column("disabled", sa.Boolean(), nullable=False, server_default=sa.false()), sa.Column("last_validated_at", sa.DateTime(timezone=True)), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_social_accounts_platform", "social_accounts", ["platform"]); op.create_index("ix_social_accounts_external_account_id", "social_accounts", ["external_account_id"])

def downgrade() -> None:
    op.drop_index("ix_social_accounts_external_account_id", table_name="social_accounts"); op.drop_index("ix_social_accounts_platform", table_name="social_accounts"); op.drop_table("social_accounts")
