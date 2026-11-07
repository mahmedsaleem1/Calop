"""remove analyses

Revision ID: 7c1e4a9d2f30
Revises: b39f3620898e
Create Date: 2026-11-07 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '7c1e4a9d2f30'
down_revision: Union[str, None] = 'b39f3620898e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_table('analyses')


def downgrade() -> None:
    op.create_table('analyses',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('capture_id', sa.Uuid(), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('provider', sa.String(length=50), nullable=True),
    sa.Column('label', sa.String(length=255), nullable=True),
    sa.Column('confidence', sa.Float(), nullable=True),
    sa.Column('calories', sa.Float(), nullable=True),
    sa.Column('protein_g', sa.Float(), nullable=True),
    sa.Column('carbs_g', sa.Float(), nullable=True),
    sa.Column('fat_g', sa.Float(), nullable=True),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('error', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['capture_id'], ['captures.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('capture_id')
    )
