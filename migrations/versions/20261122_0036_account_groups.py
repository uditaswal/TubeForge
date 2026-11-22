"""Group per-platform connections under one account (person or brand)."""
from alembic import op
import sqlalchemy as sa

revision = '20261122_0036'
down_revision = '20261108_0034'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'account_groups',
        sa.Column('id', sa.String(64), primary_key=True),
        sa.Column('name', sa.String(200), nullable=False),
        sa.Column('category', sa.String(100), nullable=False, server_default='general'),
        sa.Column('default_description', sa.Text(), nullable=False, server_default=''),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.add_column('social_accounts', sa.Column('group_id', sa.String(64)))
    op.create_index('ix_social_accounts_group_id', 'social_accounts', ['group_id'])
    # Every existing connection becomes its own account (same id), so nothing is lost
    # and the operator can add other platforms under it afterwards.
    op.execute("""
        INSERT INTO account_groups (id, name, category, default_description, created_at, updated_at)
        SELECT id, display_name, category, default_description, created_at, updated_at FROM social_accounts
    """)
    op.execute("UPDATE social_accounts SET group_id = id")


def downgrade():
    op.drop_index('ix_social_accounts_group_id', table_name='social_accounts')
    op.drop_column('social_accounts', 'group_id')
    op.drop_table('account_groups')
