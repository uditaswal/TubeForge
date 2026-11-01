"""Global batch production admission hold."""
from alembic import op
import sqlalchemy as sa
revision = '20261101_0031'
down_revision = '20261022_0030'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('batch_production_control', sa.Column('id', sa.Integer(), primary_key=True), sa.Column('hold', sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade():
    op.drop_table('batch_production_control')
