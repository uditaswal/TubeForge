"""Persist per-destination slot and an independently paused state."""
from alembic import op
import sqlalchemy as sa

revision = '20261111_0035'
down_revision = '20261111_0034'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('destination_deliveries', sa.Column('scheduled_for', sa.DateTime(timezone=True)))
    op.add_column('destination_deliveries', sa.Column('paused_from_state', sa.String(32)))
    op.add_column('destination_deliveries', sa.Column('youtube_schedule_audited', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.create_index('ix_destination_deliveries_scheduled_for', 'destination_deliveries', ['scheduled_for'])


def downgrade():
    op.drop_index('ix_destination_deliveries_scheduled_for', table_name='destination_deliveries')
    op.drop_column('destination_deliveries', 'youtube_schedule_audited')
    op.drop_column('destination_deliveries', 'paused_from_state')
    op.drop_column('destination_deliveries', 'scheduled_for')
