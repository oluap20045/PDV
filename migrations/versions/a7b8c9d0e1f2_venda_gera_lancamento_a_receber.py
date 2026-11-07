"""Venda gera lancamento a receber (forma de pagamento + vinculo)

Revision ID: a7b8c9d0e1f2
Revises: f1a2b3c4d5e6
Create Date: 2026-11-07 21:00:00

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a7b8c9d0e1f2'
down_revision = 'f1a2b3c4d5e6'
branch_labels = None
depends_on = None


def _conta_vendas(conn):
    cid = conn.execute(sa.text("SELECT id FROM conta WHERE nome = 'Venda de Produtos'")).scalar()
    if cid is None:
        gid = conn.execute(sa.text("SELECT id FROM grupo_conta WHERE nome = '1. Receitas Operacionais'")).scalar()
        if gid is None:
            conn.execute(sa.text("INSERT INTO grupo_conta (nome) VALUES ('1. Receitas Operacionais')"))
            gid = conn.execute(sa.text("SELECT id FROM grupo_conta WHERE nome = '1. Receitas Operacionais'")).scalar()
        conn.execute(sa.text("INSERT INTO conta (nome, grupo_id) VALUES ('Venda de Produtos', :g)"), {'g': gid})
        cid = conn.execute(sa.text("SELECT id FROM conta WHERE nome = 'Venda de Produtos'")).scalar()
    return cid


def upgrade():
    with op.batch_alter_table('venda', schema=None) as batch_op:
        batch_op.add_column(sa.Column('forma_pagamento', sa.String(length=20), nullable=False, server_default='Dinheiro'))
        batch_op.add_column(sa.Column('lancamento_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key('fk_venda_lancamento', 'lancamento', ['lancamento_id'], ['id'])

    # vendas que já existiam: gera o recebimento (já quitado na data da venda)
    conn = op.get_bind()
    vendas = conn.execute(sa.text(
        "SELECT v.id, v.data, v.total, c.nome FROM venda v JOIN cliente c ON c.id = v.cliente_id "
        "WHERE v.lancamento_id IS NULL")).fetchall()
    if vendas:
        conta_id = _conta_vendas(conn)
        for vid, data, total, cliente in vendas:
            conn.execute(sa.text(
                "INSERT INTO lancamento (descricao, valor, tipo, data_lancamento, data_vencimento, data_pagamento, conta_id) "
                "VALUES (:d, :v, 'RECEBER', :dt, :venc, :dt, :c)"),
                {'d': f'Venda #{vid} - {cliente}'[:200], 'v': total, 'dt': data, 'venc': data.date(), 'c': conta_id})
            lid = conn.execute(sa.text("SELECT MAX(id) FROM lancamento")).scalar()
            conn.execute(sa.text("UPDATE venda SET lancamento_id = :l WHERE id = :v"), {'l': lid, 'v': vid})


def downgrade():
    conn = op.get_bind()
    ids = [r[0] for r in conn.execute(sa.text("SELECT lancamento_id FROM venda WHERE lancamento_id IS NOT NULL"))]
    with op.batch_alter_table('venda', schema=None) as batch_op:
        batch_op.drop_constraint('fk_venda_lancamento', type_='foreignkey')
        batch_op.drop_column('lancamento_id')
        batch_op.drop_column('forma_pagamento')
    for lid in ids:
        conn.execute(sa.text("DELETE FROM lancamento WHERE id = :l"), {'l': lid})
