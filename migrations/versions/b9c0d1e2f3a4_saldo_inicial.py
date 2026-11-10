"""Saldo inicial da empresa (fluxo de caixa)

Revision ID: b9c0d1e2f3a4
Revises: a8b9c0d1e2f3
Create Date: 2026-11-10 16:00:00

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b9c0d1e2f3a4'
down_revision = 'a8b9c0d1e2f3'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('empresa', schema=None) as batch_op:
        batch_op.add_column(sa.Column('saldo_inicial', sa.Float(), nullable=False, server_default='0'))


def downgrade():
    with op.batch_alter_table('empresa', schema=None) as batch_op:
        batch_op.drop_column('saldo_inicial')
