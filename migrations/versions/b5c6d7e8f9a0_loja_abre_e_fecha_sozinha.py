"""Loja online abre e fecha sozinha (modo automático com horário e dias)

Revision ID: b5c6d7e8f9a0
Revises: a4b5c6d7e8f9
Create Date: 2026-11-12 22:00:00

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b5c6d7e8f9a0'
down_revision = 'a4b5c6d7e8f9'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('empresa', schema=None) as batch_op:
        batch_op.add_column(sa.Column('loja_modo', sa.String(length=10), nullable=False, server_default='fechada'))
        batch_op.add_column(sa.Column('loja_abre', sa.Time(), nullable=False, server_default='18:00:00'))
        batch_op.add_column(sa.Column('loja_fecha', sa.Time(), nullable=False, server_default='23:00:00'))
        batch_op.add_column(sa.Column('loja_dias', sa.String(length=7), nullable=False, server_default='0123456'))
    op.execute("UPDATE empresa SET loja_modo = CASE WHEN loja_aberta THEN 'aberta' ELSE 'fechada' END")
    with op.batch_alter_table('empresa', schema=None) as batch_op:
        batch_op.drop_column('loja_aberta')


def downgrade():
    with op.batch_alter_table('empresa', schema=None) as batch_op:
        batch_op.add_column(sa.Column('loja_aberta', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.execute("UPDATE empresa SET loja_aberta = (loja_modo <> 'fechada')")
    with op.batch_alter_table('empresa', schema=None) as batch_op:
        for c in ('loja_dias', 'loja_fecha', 'loja_abre', 'loja_modo'):
            batch_op.drop_column(c)
