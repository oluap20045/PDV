"""Combos / promoções ("4 por 12"): tabela combo, combo_produto e marcação nos itens de venda e pedido

Revision ID: e8f9a0b1c2d3
Revises: d7e8f9a0b1c2
Create Date: 2026-11-13 21:00:00

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e8f9a0b1c2d3'
down_revision = 'd7e8f9a0b1c2'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'combo',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('nome', sa.String(length=80), nullable=False),
        sa.Column('quantidade', sa.Integer(), nullable=False),
        sa.Column('preco', sa.Float(), nullable=False),
        sa.Column('ativo', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('no_pdv', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('na_loja', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('inicio', sa.Date(), nullable=True),
        sa.Column('fim', sa.Date(), nullable=True),
        sa.Column('criado_em', sa.DateTime(), nullable=False),
    )
    op.create_table(
        'combo_produto',
        sa.Column('combo_id', sa.Integer(), sa.ForeignKey('combo.id', ondelete='CASCADE'), primary_key=True),
        sa.Column('produto_id', sa.Integer(), sa.ForeignKey('produto.id', ondelete='CASCADE'), primary_key=True),
    )
    with op.batch_alter_table('item_venda', schema=None) as batch_op:
        batch_op.add_column(sa.Column('combo_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('combo_grupo', sa.SmallInteger(), nullable=True))
        batch_op.create_index('ix_item_venda_combo_id', ['combo_id'])
        batch_op.create_foreign_key('fk_item_venda_combo', 'combo', ['combo_id'], ['id'])
    with op.batch_alter_table('pedido_item', schema=None) as batch_op:
        batch_op.add_column(sa.Column('combo_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('combo_grupo', sa.SmallInteger(), nullable=True))
        batch_op.create_foreign_key('fk_pedido_item_combo', 'combo', ['combo_id'], ['id'])


def downgrade():
    with op.batch_alter_table('pedido_item', schema=None) as batch_op:
        batch_op.drop_constraint('fk_pedido_item_combo', type_='foreignkey')
        batch_op.drop_column('combo_grupo')
        batch_op.drop_column('combo_id')
    with op.batch_alter_table('item_venda', schema=None) as batch_op:
        batch_op.drop_constraint('fk_item_venda_combo', type_='foreignkey')
        batch_op.drop_index('ix_item_venda_combo_id')
        batch_op.drop_column('combo_grupo')
        batch_op.drop_column('combo_id')
    op.drop_table('combo_produto')
    op.drop_table('combo')
