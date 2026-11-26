"""Black Friday: produto.preco_normal (preço de tabela guardado), produto.black_isca e empresa.black_ativo / black_margem

Revision ID: c3d4e5f6a7b9
Revises: a1b2c3d4e5f7
Create Date: 2026-11-26 12:00:00

"""
from alembic import op
import sqlalchemy as sa


revision = 'c3d4e5f6a7b9'
down_revision = 'a1b2c3d4e5f7'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('produto', schema=None) as batch_op:
        batch_op.add_column(sa.Column('preco_normal', sa.Float(), nullable=True))
        batch_op.add_column(sa.Column('black_isca', sa.Boolean(), nullable=False, server_default=sa.false()))
    with op.batch_alter_table('empresa', schema=None) as batch_op:
        batch_op.add_column(sa.Column('black_ativo', sa.Boolean(), nullable=False, server_default=sa.false()))
        batch_op.add_column(sa.Column('black_margem', sa.Float(), nullable=False, server_default='5'))


def downgrade():
    with op.batch_alter_table('empresa', schema=None) as batch_op:
        batch_op.drop_column('black_margem')
        batch_op.drop_column('black_ativo')
    with op.batch_alter_table('produto', schema=None) as batch_op:
        batch_op.drop_column('black_isca')
        batch_op.drop_column('preco_normal')
