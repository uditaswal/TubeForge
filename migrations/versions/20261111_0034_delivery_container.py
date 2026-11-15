"""Persist a remote processing container and its expiration."""
from alembic import op
import sqlalchemy as sa

revision = '20261111_0034'
down_revision = '20261111_0033'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('destination_deliveries', sa.Column('remote_session_expires_at', sa.DateTime(timezone=True)))
    op.add_column('destination_deliveries', sa.Column('remote_container_id', sa.String(500)))


def downgrade():
    op.drop_column('destination_deliveries', 'remote_container_id')
    op.drop_column('destination_deliveries', 'remote_session_expires_at')
