"""Immutable reference intake revisions and fenced acquisition activity."""
from alembic import op
import sqlalchemy as sa
revision='20261108_0033'
down_revision='20261105_0032'
branch_labels=None
depends_on=None


def upgrade():
    op.create_table('reference_intake_revisions',
        sa.Column('row_id',sa.String(64),primary_key=True),
        sa.Column('intake_id',sa.String(64),nullable=False,index=True),
        sa.Column('revision',sa.Integer(),nullable=False),
        sa.Column('request_key',sa.String(64),nullable=False,index=True),
        sa.Column('capture_key',sa.String(64),nullable=False,index=True),
        sa.Column('request_json',sa.Text(),nullable=False),sa.Column('state',sa.String(32),nullable=False),
        sa.Column('snapshot_json',sa.Text()),sa.Column('snapshot_sha256',sa.String(64)),
        sa.Column('failure_code',sa.String(40)),sa.Column('message',sa.Text()),
        sa.Column('force_refresh',sa.Boolean(),nullable=False),sa.Column('cache_hit',sa.Boolean(),nullable=False),
        sa.Column('claim_owner',sa.String(128)),sa.Column('claim_token',sa.String(64)),sa.Column('lease_expires_at',sa.DateTime(timezone=True)),
        sa.Column('created_at',sa.DateTime(timezone=True),nullable=False),sa.Column('finished_at',sa.DateTime(timezone=True)),
        sa.UniqueConstraint('intake_id','revision',name='uq_reference_intake_revision'))
    op.create_table('reference_intake_events',sa.Column('id',sa.Integer(),primary_key=True,autoincrement=True),
        sa.Column('intake_id',sa.String(64),nullable=False,index=True),sa.Column('revision',sa.Integer(),nullable=False),
        sa.Column('event',sa.String(64),nullable=False),sa.Column('actor',sa.String(128),nullable=False),
        sa.Column('details_json',sa.Text(),nullable=False),sa.Column('created_at',sa.DateTime(timezone=True),nullable=False))


def downgrade():
    op.drop_table('reference_intake_events')
    op.drop_table('reference_intake_revisions')
