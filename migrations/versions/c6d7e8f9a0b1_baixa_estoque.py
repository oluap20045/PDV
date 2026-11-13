"""Baixa de estoque sem venda (brinde, perda, vencido...)

Revision ID: c6d7e8f9a0b1
Revises: b5c6d7e8f9a0
Create Date: 2026-11-13 10:00:00

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c6d7e8f9a0b1'
down_revision = 'b5c6d7e8f9a0'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'baixa_estoque',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('data', sa.DateTime(), nullable=False),
        sa.Column('produto_id', sa.Integer(), nullable=False),
        sa.Column('quantidade', sa.Integer(), nullable=False),
        sa.Column('custo_unitario', sa.Float(), nullable=False, server_default='0'),
        sa.Column('motivo', sa.String(length=20), nullable=False),
        sa.Column('observacao', sa.String(length=255), nullable=True),
        sa.Column('cliente_id', sa.Integer(), nullable=True),
        sa.Column('usuario_id', sa.Integer(), nullable=True),
        sa.Column('estornada_em', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['produto_id'], ['produto.id'], name='fk_baixa_produto'),
        sa.ForeignKeyConstraint(['cliente_id'], ['cliente.id'], name='fk_baixa_cliente'),
        sa.ForeignKeyConstraint(['usuario_id'], ['usuario.id'], name='fk_baixa_usuario'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_baixa_estoque_data', 'baixa_estoque', ['data'])
    op.create_index('ix_baixa_estoque_produto_id', 'baixa_estoque', ['produto_id'])
    op.create_index('ix_baixa_estoque_motivo', 'baixa_estoque', ['motivo'])


def downgrade():
    # apagar a tabela leva os índices junto (MariaDB não apaga índice usado por chave estrangeira)
    op.drop_table('baixa_estoque')
