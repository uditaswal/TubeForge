"""Audited Studio script-routing policy for future jobs."""
from alembic import op
import sqlalchemy as sa
revision = '20261105_0032'
down_revision = '20261101_0031'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('script_routing_policies',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('mode', sa.String(24), nullable=False),
        sa.Column('preferred_model', sa.String(32), nullable=False),
        sa.Column('actor', sa.String(100), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False))


def downgrade():
    op.drop_table('script_routing_policies')
