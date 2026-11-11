"""Pedidos de clientes, ordens de compra e preço de tabela no item de venda (desconto)

Revision ID: d1e2f3a4b5c6
Revises: c0d1e2f3a4b5
Create Date: 2026-11-10 23:30:00

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd1e2f3a4b5c6'
down_revision = 'c0d1e2f3a4b5'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'pedido',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('cliente_id', sa.Integer(), nullable=False),
        sa.Column('criado_em', sa.DateTime(), nullable=False),
        sa.Column('previsao', sa.Date(), nullable=True),
        sa.Column('observacao', sa.String(length=255), nullable=True),
        sa.Column('status', sa.String(length=12), nullable=False, server_default='aberto'),
        sa.Column('venda_id', sa.Integer(), nullable=True),
        sa.Column('usuario_id', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['cliente_id'], ['cliente.id'], name='fk_pedido_cliente'),
        sa.ForeignKeyConstraint(['venda_id'], ['venda.id'], name='fk_pedido_venda'),
        sa.ForeignKeyConstraint(['usuario_id'], ['usuario.id'], name='fk_pedido_usuario'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_pedido_cliente_id', 'pedido', ['cliente_id'])
    op.create_index('ix_pedido_status', 'pedido', ['status'])
    op.create_table(
        'pedido_item',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('pedido_id', sa.Integer(), nullable=False),
        sa.Column('produto_id', sa.Integer(), nullable=False),
        sa.Column('quantidade', sa.Integer(), nullable=False),
        sa.Column('preco_unitario', sa.Float(), nullable=False),
        sa.ForeignKeyConstraint(['pedido_id'], ['pedido.id'], name='fk_pedido_item_pedido'),
        sa.ForeignKeyConstraint(['produto_id'], ['produto.id'], name='fk_pedido_item_produto'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_pedido_item_pedido_id', 'pedido_item', ['pedido_id'])
    op.create_table(
        'ordem_compra',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('criado_em', sa.DateTime(), nullable=False),
        sa.Column('fornecedor_id', sa.Integer(), nullable=True),
        sa.Column('status', sa.String(length=12), nullable=False, server_default='aberta'),
        sa.Column('compra_id', sa.Integer(), nullable=True),
        sa.Column('observacao', sa.String(length=255), nullable=True),
        sa.ForeignKeyConstraint(['fornecedor_id'], ['fornecedor.id'], name='fk_ordem_compra_fornecedor'),
        sa.ForeignKeyConstraint(['compra_id'], ['compra.id'], name='fk_ordem_compra_compra'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_ordem_compra_status', 'ordem_compra', ['status'])
    op.create_table(
        'ordem_compra_item',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('ordem_id', sa.Integer(), nullable=False),
        sa.Column('produto_id', sa.Integer(), nullable=False),
        sa.Column('quantidade', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['ordem_id'], ['ordem_compra.id'], name='fk_ordem_item_ordem'),
        sa.ForeignKeyConstraint(['produto_id'], ['produto.id'], name='fk_ordem_item_produto'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_ordem_compra_item_ordem_id', 'ordem_compra_item', ['ordem_id'])
    with op.batch_alter_table('item_venda', schema=None) as batch_op:
        batch_op.add_column(sa.Column('preco_tabela', sa.Float(), nullable=True))


def downgrade():
    with op.batch_alter_table('item_venda', schema=None) as batch_op:
        batch_op.drop_column('preco_tabela')
    # apagar a tabela leva junto os índices (no MariaDB não dá para apagar índice usado por chave estrangeira)
    op.drop_table('ordem_compra_item')
    op.drop_table('ordem_compra')
    op.drop_table('pedido_item')
    op.drop_table('pedido')
