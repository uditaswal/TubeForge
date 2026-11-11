"""Conservative daily YouTube upload quota reservations."""
from alembic import op
import sqlalchemy as sa

revision = '20261111_0033'
down_revision = '20261105_0032'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'youtube_quota_charges',
        sa.Column('id', sa.String(64), primary_key=True),
        sa.Column('quota_day', sa.String(10), nullable=False),
        sa.Column('delivery_id', sa.String(64), nullable=False),
        sa.Column('units', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint('quota_day', 'delivery_id', name='uq_youtube_quota_day_delivery'),
    )
    op.create_index('ix_youtube_quota_charges_quota_day', 'youtube_quota_charges', ['quota_day'])


def downgrade():
    op.drop_index('ix_youtube_quota_charges_quota_day', table_name='youtube_quota_charges')
    op.drop_table('youtube_quota_charges')
