"""Loja online: fotos e visibilidade dos produtos, origem/entrega/pagamento do pedido, Pix e configuração

Revision ID: f3a4b5c6d7e8
Revises: e2f3a4b5c6d7
Create Date: 2026-11-12 10:00:00

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql


# revision identifiers, used by Alembic.
revision = 'f3a4b5c6d7e8'
down_revision = 'e2f3a4b5c6d7'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('produto', schema=None) as batch_op:
        batch_op.add_column(sa.Column('na_loja', sa.Boolean(), nullable=False, server_default=sa.true()))
        batch_op.add_column(sa.Column('descricao', sa.String(length=300), nullable=True))

    op.create_table(
        'produto_foto',
        sa.Column('produto_id', sa.Integer(), sa.ForeignKey('produto.id'), primary_key=True),
        sa.Column('dados', sa.LargeBinary().with_variant(mysql.MEDIUMBLOB(), 'mysql', 'mariadb'), nullable=False),
        sa.Column('mime', sa.String(length=20), nullable=False),
        sa.Column('atualizado_em', sa.DateTime(), nullable=False),
    )

    with op.batch_alter_table('pedido', schema=None) as batch_op:
        batch_op.add_column(sa.Column('origem', sa.String(length=10), nullable=False, server_default='balcao'))
        batch_op.add_column(sa.Column('codigo', sa.String(length=16), nullable=True))
        batch_op.add_column(sa.Column('entrega', sa.String(length=120), nullable=True))
        batch_op.add_column(sa.Column('pagamento', sa.String(length=30), nullable=True))
        batch_op.create_index('ix_pedido_origem', ['origem'])
        batch_op.create_unique_constraint('uq_pedido_codigo', ['codigo'])

    with op.batch_alter_table('empresa', schema=None) as batch_op:
        batch_op.add_column(sa.Column('loja_aberta', sa.Boolean(), nullable=False, server_default=sa.false()))
        batch_op.add_column(sa.Column('loja_aviso', sa.String(length=300), nullable=True))
        batch_op.add_column(sa.Column('loja_whatsapp', sa.String(length=13), nullable=True))
        batch_op.add_column(sa.Column('pix_chave', sa.String(length=77), nullable=True))
        batch_op.add_column(sa.Column('pix_nome', sa.String(length=25), nullable=True))
        batch_op.add_column(sa.Column('pix_cidade', sa.String(length=15), nullable=True))


def downgrade():
    with op.batch_alter_table('empresa', schema=None) as batch_op:
        for c in ('pix_cidade', 'pix_nome', 'pix_chave', 'loja_whatsapp', 'loja_aviso', 'loja_aberta'):
            batch_op.drop_column(c)
    with op.batch_alter_table('pedido', schema=None) as batch_op:
        batch_op.drop_constraint('uq_pedido_codigo', type_='unique')
        batch_op.drop_index('ix_pedido_origem')
        for c in ('pagamento', 'entrega', 'codigo', 'origem'):
            batch_op.drop_column(c)
    op.drop_table('produto_foto')
    with op.batch_alter_table('produto', schema=None) as batch_op:
        batch_op.drop_column('descricao')
        batch_op.drop_column('na_loja')
