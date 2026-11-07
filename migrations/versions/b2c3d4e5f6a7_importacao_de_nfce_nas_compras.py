"""Importacao de NFC-e nas compras (chave de acesso, CNPJ do fornecedor, vinculos de produto)

Revision ID: b2c3d4e5f6a7
Revises: a7b8c9d0e1f2
Create Date: 2026-11-07 22:00:00

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b2c3d4e5f6a7'
down_revision = 'a7b8c9d0e1f2'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('fornecedor', schema=None) as batch_op:
        batch_op.add_column(sa.Column('cnpj', sa.String(length=14), nullable=True))
        batch_op.create_unique_constraint('uq_fornecedor_cnpj', ['cnpj'])
    with op.batch_alter_table('compra', schema=None) as batch_op:
        batch_op.add_column(sa.Column('chave_acesso', sa.String(length=44), nullable=True))
        batch_op.create_unique_constraint('uq_compra_chave_acesso', ['chave_acesso'])
    op.create_table(
        'produto_vinculo_nfce',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('cnpj', sa.String(length=14), nullable=False, server_default=''),
        sa.Column('codigo', sa.String(length=60), nullable=False, server_default=''),
        sa.Column('descricao', sa.String(length=200), nullable=False),
        sa.Column('produto_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['produto_id'], ['produto.id'], name='fk_vinculo_nfce_produto'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('cnpj', 'codigo', 'descricao', name='uq_vinculo_nfce'),
    )
    with op.batch_alter_table('produto_vinculo_nfce', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_produto_vinculo_nfce_descricao'), ['descricao'], unique=False)


def downgrade():
    op.drop_table('produto_vinculo_nfce')
    with op.batch_alter_table('compra', schema=None) as batch_op:
        batch_op.drop_constraint('uq_compra_chave_acesso', type_='unique')
        batch_op.drop_column('chave_acesso')
    with op.batch_alter_table('fornecedor', schema=None) as batch_op:
        batch_op.drop_constraint('uq_fornecedor_cnpj', type_='unique')
        batch_op.drop_column('cnpj')
