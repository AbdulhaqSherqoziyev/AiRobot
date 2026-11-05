"""experiments and AI research reports. Adds tables only; existing tables are untouched.

Revision ID: 0003
Revises: 0002
"""
from alembic import op
import sqlalchemy as sa


revision = '0003'
down_revision = '0002'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('experiments',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('job_id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=128), nullable=False),
    sa.Column('strategy_key', sa.String(length=64), nullable=False),
    sa.Column('strategy_version', sa.String(length=16), nullable=False),
    sa.Column('pairs', sa.JSON(), nullable=False),
    sa.Column('timeframe', sa.String(length=8), nullable=False),
    sa.Column('start_ts', sa.Integer(), nullable=False),
    sa.Column('end_ts', sa.Integer(), nullable=False),
    sa.Column('backend', sa.String(length=16), nullable=False),
    sa.Column('grid', sa.JSON(), nullable=False),
    sa.Column('config', sa.JSON(), nullable=False),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('error', sa.Text(), nullable=False),
    sa.Column('n_combos', sa.Integer(), nullable=False),
    sa.Column('runtime_s', sa.Float(), nullable=True),
    sa.Column('repro', sa.JSON(), nullable=False),
    sa.Column('summary', sa.JSON(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['job_id'], ['jobs.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('experiments', schema=None) as b:
        for c in ('backend', 'created_at', 'job_id', 'status', 'strategy_key'):
            b.create_index(b.f(f'ix_experiments_{c}'), [c], unique=False)

    op.create_table('experiment_results',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('experiment_id', sa.Integer(), nullable=False),
    sa.Column('rank', sa.Integer(), nullable=False),
    sa.Column('selected', sa.Boolean(), nullable=False),
    sa.Column('params', sa.JSON(), nullable=False),
    sa.Column('train', sa.JSON(), nullable=False),
    sa.Column('validation', sa.JSON(), nullable=False),
    sa.Column('per_pair', sa.JSON(), nullable=False),
    sa.ForeignKeyConstraint(['experiment_id'], ['experiments.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('experiment_results', schema=None) as b:
        b.create_index(b.f('ix_experiment_results_experiment_id'), ['experiment_id'], unique=False)

    op.create_table('ai_reports',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('pair', sa.String(length=32), nullable=False),
    sa.Column('timeframe', sa.String(length=8), nullable=False),
    sa.Column('engine', sa.String(length=24), nullable=False),
    sa.Column('model', sa.String(length=64), nullable=True),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('error', sa.Text(), nullable=False),
    sa.Column('data_pack', sa.JSON(), nullable=False),
    sa.Column('recommendation', sa.JSON(), nullable=False),
    sa.Column('raw', sa.Text(), nullable=False),
    sa.Column('usage', sa.JSON(), nullable=True),
    sa.Column('latency_s', sa.Float(), nullable=True),
    sa.Column('last_candle_ts', sa.Integer(), nullable=False),
    sa.Column('reference_price', sa.Float(), nullable=False),
    sa.Column('outcome', sa.JSON(), nullable=True),
    sa.Column('outcome_at', sa.DateTime(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('ai_reports', schema=None) as b:
        for c in ('created_at', 'engine', 'pair', 'status'):
            b.create_index(b.f(f'ix_ai_reports_{c}'), [c], unique=False)


def downgrade():
    op.drop_table('ai_reports')
    op.drop_table('experiment_results')
    op.drop_table('experiments')
