"""Taxas de cartao e venda com varias formas de pagamento

Revision ID: c4d5e6f7a8b9
Revises: b2c3d4e5f6a7
Create Date: 2026-11-07 23:00:00

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c4d5e6f7a8b9'
down_revision = 'b2c3d4e5f6a7'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'taxa_pagamento',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('forma', sa.String(length=30), nullable=False),
        sa.Column('bandeira', sa.String(length=30), nullable=True),
        sa.Column('parcelas_de', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('parcelas_ate', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('percentual', sa.Float(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_table(
        'venda_pagamento',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('venda_id', sa.Integer(), nullable=False),
        sa.Column('forma', sa.String(length=30), nullable=False),
        sa.Column('bandeira', sa.String(length=30), nullable=True),
        sa.Column('parcelas', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('valor', sa.Float(), nullable=False),
        sa.Column('taxa_percentual', sa.Float(), nullable=False, server_default='0'),
        sa.Column('taxa_valor', sa.Float(), nullable=False, server_default='0'),
        sa.Column('lancamento_id', sa.Integer(), nullable=True),
        sa.Column('lancamento_taxa_id', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['venda_id'], ['venda.id'], name='fk_vpag_venda'),
        sa.ForeignKeyConstraint(['lancamento_id'], ['lancamento.id'], name='fk_vpag_lancamento'),
        sa.ForeignKeyConstraint(['lancamento_taxa_id'], ['lancamento.id'], name='fk_vpag_lancamento_taxa'),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('venda_pagamento', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_venda_pagamento_venda_id'), ['venda_id'], unique=False)

    with op.batch_alter_table('venda', schema=None) as batch_op:
        batch_op.add_column(sa.Column('taxa_total', sa.Float(), nullable=False, server_default='0'))
        batch_op.alter_column('forma_pagamento', existing_type=sa.String(length=20), type_=sa.String(length=120),
                              existing_nullable=False)

    # vendas antigas: a forma única + o lançamento viram uma linha de pagamento
    conn = op.get_bind()
    conn.execute(sa.text(
        "INSERT INTO venda_pagamento (venda_id, forma, parcelas, valor, taxa_percentual, taxa_valor, lancamento_id) "
        "SELECT id, SUBSTR(forma_pagamento, 1, 30), 1, total, 0, 0, lancamento_id FROM venda"))

    with op.batch_alter_table('venda', schema=None) as batch_op:
        batch_op.drop_constraint('fk_venda_lancamento', type_='foreignkey')
        batch_op.drop_column('lancamento_id')

    # conta da taxa (vem do plano padrão; garante caso tenha sido apagada)
    if conn.execute(sa.text("SELECT id FROM conta WHERE nome = 'Taxas de Cartão/Maquininha'")).scalar() is None:
        gid = conn.execute(sa.text("SELECT id FROM grupo_conta WHERE nome = '6. Despesas Comerciais'")).scalar()
        if gid is None:
            conn.execute(sa.text("INSERT INTO grupo_conta (nome) VALUES ('6. Despesas Comerciais')"))
            gid = conn.execute(sa.text("SELECT id FROM grupo_conta WHERE nome = '6. Despesas Comerciais'")).scalar()
        conn.execute(sa.text("INSERT INTO conta (nome, grupo_id) VALUES ('Taxas de Cartão/Maquininha', :g)"), {'g': gid})


def downgrade():
    with op.batch_alter_table('venda', schema=None) as batch_op:
        batch_op.add_column(sa.Column('lancamento_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key('fk_venda_lancamento', 'lancamento', ['lancamento_id'], ['id'])
    conn = op.get_bind()
    conn.execute(sa.text(
        "UPDATE venda SET lancamento_id = (SELECT MIN(lancamento_id) FROM venda_pagamento vp WHERE vp.venda_id = venda.id)"))
    with op.batch_alter_table('venda', schema=None) as batch_op:
        batch_op.drop_column('taxa_total')
    op.drop_table('venda_pagamento')
    op.drop_table('taxa_pagamento')
