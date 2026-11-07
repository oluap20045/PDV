"""Adiciona codigo de barras ao produto

Revision ID: c3a1f0d2b7e4
Revises: bae1460fae8b
Create Date: 2026-11-07 19:10:00

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c3a1f0d2b7e4'
down_revision = 'bae1460fae8b'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('produto', schema=None) as batch_op:
        batch_op.add_column(sa.Column('codigo_barras', sa.String(length=50), nullable=True))
        batch_op.create_index(batch_op.f('ix_produto_codigo_barras'), ['codigo_barras'], unique=True)


def downgrade():
    with op.batch_alter_table('produto', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_produto_codigo_barras'))
        batch_op.drop_column('codigo_barras')
