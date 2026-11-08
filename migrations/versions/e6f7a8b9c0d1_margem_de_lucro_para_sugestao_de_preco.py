"""Margem de lucro desejada (sugestao de preco)

Revision ID: e6f7a8b9c0d1
Revises: d5e6f7a8b9c0
Create Date: 2026-11-08 10:00:00

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e6f7a8b9c0d1'
down_revision = 'd5e6f7a8b9c0'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('empresa', schema=None) as batch_op:
        batch_op.add_column(sa.Column('margem_lucro', sa.Float(), nullable=False, server_default='30'))


def downgrade():
    with op.batch_alter_table('empresa', schema=None) as batch_op:
        batch_op.drop_column('margem_lucro')
