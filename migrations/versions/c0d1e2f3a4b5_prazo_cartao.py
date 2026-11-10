"""Prazo de deposito da maquininha (D+N)

Revision ID: c0d1e2f3a4b5
Revises: b9c0d1e2f3a4
Create Date: 2026-11-10 17:00:00

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c0d1e2f3a4b5'
down_revision = 'b9c0d1e2f3a4'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('empresa', schema=None) as batch_op:
        batch_op.add_column(sa.Column('prazo_cartao', sa.Integer(), nullable=False, server_default='1'))


def downgrade():
    with op.batch_alter_table('empresa', schema=None) as batch_op:
        batch_op.drop_column('prazo_cartao')
