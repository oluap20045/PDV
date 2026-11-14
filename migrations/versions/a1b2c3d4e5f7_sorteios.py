"""Sorteios: tabelas sorteio e sorteio_inscricao; cliente ganha bloco, apartamento e origem

Revision ID: a1b2c3d4e5f7
Revises: f9a0b1c2d3e4
Create Date: 2026-11-14 18:00:00

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a1b2c3d4e5f7'
down_revision = 'f9a0b1c2d3e4'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('cliente', schema=None) as batch_op:
        batch_op.add_column(sa.Column('bloco', sa.String(length=6), nullable=True))
        batch_op.add_column(sa.Column('apartamento', sa.String(length=8), nullable=True))
        batch_op.add_column(sa.Column('origem', sa.String(length=12), nullable=True))
        batch_op.create_index('ix_cliente_bloco_apto', ['bloco', 'apartamento'])
    op.create_table(
        'sorteio',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('codigo', sa.String(length=16), nullable=False, unique=True),
        sa.Column('premio', sa.String(length=120), nullable=False),
        sa.Column('descricao', sa.String(length=300), nullable=True),
        sa.Column('produto_id', sa.Integer(), sa.ForeignKey('produto.id', ondelete='SET NULL'), nullable=True),
        sa.Column('quantidade', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('baixa_id', sa.Integer(), sa.ForeignKey('baixa_estoque.id', ondelete='SET NULL'), nullable=True),
        sa.Column('inicio', sa.DateTime(), nullable=False),
        sa.Column('fim', sa.DateTime(), nullable=False),
        sa.Column('criado_em', sa.DateTime(), nullable=False),
    )
    op.create_table(
        'sorteio_inscricao',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('sorteio_id', sa.Integer(), sa.ForeignKey('sorteio.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('cliente_id', sa.Integer(), sa.ForeignKey('cliente.id'), nullable=False, index=True),
        sa.Column('criado_em', sa.DateTime(), nullable=False),
        sa.Column('sorteado_em', sa.DateTime(), nullable=True),
        sa.UniqueConstraint('sorteio_id', 'cliente_id', name='uq_sorteio_cliente'),
    )


def downgrade():
    op.drop_table('sorteio_inscricao')
    op.drop_table('sorteio')
    with op.batch_alter_table('cliente', schema=None) as batch_op:
        batch_op.drop_index('ix_cliente_bloco_apto')
        batch_op.drop_column('origem')
        batch_op.drop_column('apartamento')
        batch_op.drop_column('bloco')
