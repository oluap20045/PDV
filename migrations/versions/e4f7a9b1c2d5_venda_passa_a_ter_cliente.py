"""Venda passa a ter cliente (com cliente padrao Consumidor final)

Revision ID: e4f7a9b1c2d5
Revises: d8e2b4c6a1f3
Create Date: 2026-11-07 20:00:00

"""
from datetime import datetime

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e4f7a9b1c2d5'
down_revision = 'd8e2b4c6a1f3'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('cliente', schema=None) as batch_op:
        batch_op.add_column(sa.Column('padrao', sa.Boolean(), nullable=False, server_default=sa.false()))

    # cria o cliente padrão e usa ele nas vendas que já existem
    conn = op.get_bind()
    conn.execute(sa.text(
        "INSERT INTO cliente (nome, padrao, criado_em) VALUES ('Consumidor final', :t, :agora)"
    ), {'t': True, 'agora': datetime.now()})
    padrao_id = conn.execute(sa.text("SELECT id FROM cliente WHERE padrao = :t"), {'t': True}).scalar()

    with op.batch_alter_table('venda', schema=None) as batch_op:
        batch_op.add_column(sa.Column('cliente_id', sa.Integer(), nullable=True))
    conn.execute(sa.text("UPDATE venda SET cliente_id = :id"), {'id': padrao_id})
    with op.batch_alter_table('venda', schema=None) as batch_op:
        batch_op.alter_column('cliente_id', existing_type=sa.Integer(), nullable=False)
        batch_op.create_index(batch_op.f('ix_venda_cliente_id'), ['cliente_id'], unique=False)
        batch_op.create_foreign_key('fk_venda_cliente', 'cliente', ['cliente_id'], ['id'])


def downgrade():
    with op.batch_alter_table('venda', schema=None) as batch_op:
        batch_op.drop_constraint('fk_venda_cliente', type_='foreignkey')
        batch_op.drop_index(batch_op.f('ix_venda_cliente_id'))
        batch_op.drop_column('cliente_id')
    op.execute(sa.text("DELETE FROM cliente WHERE padrao = :t").bindparams(t=True))
    with op.batch_alter_table('cliente', schema=None) as batch_op:
        batch_op.drop_column('padrao')
