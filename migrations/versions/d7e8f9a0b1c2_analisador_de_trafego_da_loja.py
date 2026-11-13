"""Analisador de tráfego da loja online (tabela loja_evento)

Revision ID: d7e8f9a0b1c2
Revises: c6d7e8f9a0b1
Create Date: 2026-11-13 20:00:00

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd7e8f9a0b1c2'
down_revision = 'c6d7e8f9a0b1'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'loja_evento',
        sa.Column('id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), primary_key=True, autoincrement=True),
        sa.Column('criado_em', sa.DateTime(), nullable=False),
        sa.Column('visitante', sa.String(length=24), nullable=False),
        sa.Column('tipo', sa.String(length=20), nullable=False),
        sa.Column('alvo', sa.String(length=120), nullable=True),
        sa.Column('produto_id', sa.Integer(), nullable=True),
        sa.Column('pagina', sa.String(length=20), nullable=True),
        sa.Column('origem', sa.String(length=40), nullable=True),
        sa.Column('dispositivo', sa.String(length=12), nullable=True),
    )
    with op.batch_alter_table('loja_evento', schema=None) as batch_op:
        batch_op.create_index('ix_loja_evento_criado_em', ['criado_em'])
        batch_op.create_index('ix_loja_evento_visitante', ['visitante'])
        batch_op.create_index('ix_loja_evento_tipo', ['tipo'])
        batch_op.create_index('ix_loja_evento_produto_id', ['produto_id'])


def downgrade():
    op.drop_table('loja_evento')
