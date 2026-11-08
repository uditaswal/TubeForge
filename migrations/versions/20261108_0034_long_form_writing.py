"""Durable LF2 reservations, immutable call evidence and exact script decisions."""
from alembic import op
import sqlalchemy as sa
revision='20261108_0034'
down_revision='20261108_0033'
branch_labels=None
depends_on=None


def upgrade():
    op.create_table('long_form_writing_runs',
        sa.Column('id',sa.String(32),primary_key=True),sa.Column('brief_sha256',sa.String(64),nullable=False,unique=True),
        sa.Column('intake_id',sa.String(64),nullable=False),sa.Column('intake_revision',sa.Integer(),nullable=False),
        sa.Column('initial_request_json',sa.Text(),nullable=False),sa.Column('request_json',sa.Text(),nullable=False),
        sa.Column('reference_json',sa.Text(),nullable=False),sa.Column('reference_sha256',sa.String(64),nullable=False),
        sa.Column('source_packet_json',sa.Text()),sa.Column('ledger_json',sa.Text(),nullable=False),sa.Column('token_policy_json',sa.Text(),nullable=False),
        sa.Column('reserved_tokens',sa.Integer(),nullable=False),sa.Column('expected_model',sa.String(100)),sa.Column('state',sa.String(32),nullable=False,index=True),sa.Column('next_stage',sa.String(16)),
        sa.Column('draft_json',sa.Text()),sa.Column('draft_sha256',sa.String(64)),sa.Column('draft_call_id',sa.String(64)),sa.Column('planning_json',sa.Text()),sa.Column('score_report_json',sa.Text()),sa.Column('review_json',sa.Text()),sa.Column('reviewed_draft_sha256',sa.String(64)),
        sa.Column('message',sa.Text()),sa.Column('claim_owner',sa.String(128)),sa.Column('claim_token',sa.String(64)),sa.Column('lease_expires_at',sa.DateTime(timezone=True)),
        sa.Column('created_at',sa.DateTime(timezone=True),nullable=False),sa.Column('updated_at',sa.DateTime(timezone=True),nullable=False))
    op.create_table('long_form_stage_calls',
        sa.Column('id',sa.String(64),primary_key=True),sa.Column('run_id',sa.String(32),nullable=False,index=True),sa.Column('ordinal',sa.Integer(),nullable=False),
        sa.Column('stage',sa.String(16),nullable=False),sa.Column('state',sa.String(24),nullable=False),sa.Column('payload_json',sa.Text(),nullable=False),sa.Column('payload_sha256',sa.String(64),nullable=False),
        sa.Column('admission_json',sa.Text(),nullable=False),sa.Column('reservation_tokens',sa.Integer(),nullable=False),sa.Column('charged_tokens',sa.Integer(),nullable=False),sa.Column('provider',sa.String(32),nullable=False),sa.Column('model',sa.String(100)),
        sa.Column('response_json',sa.Text()),sa.Column('failure_message',sa.Text()),sa.Column('invocation_started',sa.Boolean()),sa.Column('usage_json',sa.Text()),
        sa.Column('created_at',sa.DateTime(timezone=True),nullable=False),sa.Column('finished_at',sa.DateTime(timezone=True)),
        sa.UniqueConstraint('run_id','stage',name='uq_long_form_stage'),sa.UniqueConstraint('run_id','ordinal',name='uq_long_form_call_ordinal'))
    op.create_table('long_form_writing_decisions',sa.Column('id',sa.String(32),primary_key=True),sa.Column('run_id',sa.String(32),nullable=False,index=True),
        sa.Column('draft_sha256',sa.String(64),nullable=False),sa.Column('review_identity',sa.String(64),nullable=False),sa.Column('decision',sa.String(16),nullable=False),sa.Column('actor',sa.String(128),nullable=False),sa.Column('created_at',sa.DateTime(timezone=True),nullable=False))
    op.create_table('long_form_writing_events',sa.Column('id',sa.Integer(),primary_key=True,autoincrement=True),sa.Column('run_id',sa.String(32),nullable=False,index=True),
        sa.Column('event',sa.String(64),nullable=False),sa.Column('actor',sa.String(128),nullable=False),sa.Column('details_json',sa.Text(),nullable=False),sa.Column('created_at',sa.DateTime(timezone=True),nullable=False))


def downgrade():
    for table in ['long_form_writing_events','long_form_writing_decisions','long_form_stage_calls','long_form_writing_runs']:op.drop_table(table)
