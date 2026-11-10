"""Produto: codigo do fornecedor (catalogo) e categoria

Revision ID: a8b9c0d1e2f3
Revises: f7a8b9c0d1e2
Create Date: 2026-11-10 10:00:00

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a8b9c0d1e2f3'
down_revision = 'f7a8b9c0d1e2'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('produto', schema=None) as batch_op:
        batch_op.add_column(sa.Column('codigo_fornecedor', sa.String(length=20), nullable=True))
        batch_op.add_column(sa.Column('categoria', sa.String(length=60), nullable=True))
        batch_op.create_unique_constraint('uq_produto_codigo_fornecedor', ['codigo_fornecedor'])


def downgrade():
    with op.batch_alter_table('produto', schema=None) as batch_op:
        batch_op.drop_constraint('uq_produto_codigo_fornecedor', type_='unique')
        batch_op.drop_column('categoria')
        batch_op.drop_column('codigo_fornecedor')
