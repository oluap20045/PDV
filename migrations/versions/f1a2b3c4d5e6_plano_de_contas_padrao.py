"""Plano de contas padrao (receitas e despesas comuns de pequena empresa)

Revision ID: f1a2b3c4d5e6
Revises: e4f7a9b1c2d5
Create Date: 2026-11-07 20:30:00

So insere grupo/conta que ainda nao existe (nome e unico): nao duplica nem
mexe no que o usuario ja criou.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f1a2b3c4d5e6'
down_revision = 'e4f7a9b1c2d5'
branch_labels = None
depends_on = None


PLANO = {
    '1. Receitas Operacionais': [
        'Venda de Produtos', 'Venda por Encomenda', 'Venda para Revenda (Atacado)', 'Prestação de Serviços',
    ],
    '2. Outras Receitas': [
        'Rendimentos de Aplicações', 'Aporte dos Sócios', 'Empréstimos Recebidos', 'Outras Receitas',
    ],
    '3. Custos (CMV)': [
        'Matéria-Prima', 'Mercadorias para Revenda', 'Embalagens', 'Frete sobre Compras',
    ],
    '4. Despesas com Pessoal': [
        'Salários', 'Pró-labore', 'Encargos (INSS/FGTS)', 'Vale-Transporte',
        'Vale-Refeição/Alimentação', 'Comissões', 'Férias e 13º Salário', 'Serviços de Terceiros/Freelancers',
    ],
    '5. Despesas Administrativas': [
        'Aluguel', 'Condomínio', 'Energia Elétrica', 'Água e Esgoto', 'Gás', 'Internet e Telefone',
        'Contabilidade', 'Sistemas e Assinaturas', 'Material de Escritório', 'Material de Limpeza',
        'Manutenção e Reparos', 'Seguros',
    ],
    '6. Despesas Comerciais': [
        'Marketing e Publicidade', 'Taxas de Cartão/Maquininha', 'Taxas de Apps de Delivery',
        'Frete sobre Vendas', 'Brindes e Degustação',
    ],
    '7. Impostos e Taxas': [
        'DAS (Simples Nacional)', 'MEI (DAS-MEI)', 'Alvarás e Licenças', 'IPTU', 'Outros Impostos',
    ],
    '8. Despesas Financeiras': [
        'Tarifas Bancárias', 'Juros e Multas', 'Parcelas de Empréstimos',
    ],
    '9. Investimentos': [
        'Máquinas e Equipamentos', 'Móveis e Utensílios', 'Reformas e Instalações',
    ],
}


def upgrade():
    conn = op.get_bind()
    for grupo, contas in PLANO.items():
        gid = conn.execute(sa.text("SELECT id FROM grupo_conta WHERE nome = :n"), {'n': grupo}).scalar()
        if gid is None:
            conn.execute(sa.text("INSERT INTO grupo_conta (nome) VALUES (:n)"), {'n': grupo})
            gid = conn.execute(sa.text("SELECT id FROM grupo_conta WHERE nome = :n"), {'n': grupo}).scalar()
        for conta in contas:
            existe = conn.execute(sa.text("SELECT 1 FROM conta WHERE nome = :n"), {'n': conta}).scalar()
            if not existe:
                conn.execute(sa.text("INSERT INTO conta (nome, grupo_id) VALUES (:n, :g)"), {'n': conta, 'g': gid})


def downgrade():
    # remove só o que veio do plano padrão e não tem lançamento
    conn = op.get_bind()
    for grupo, contas in PLANO.items():
        for conta in contas:
            conn.execute(sa.text(
                "DELETE FROM conta WHERE nome = :n AND id NOT IN (SELECT conta_id FROM lancamento)"
            ), {'n': conta})
        conn.execute(sa.text(
            "DELETE FROM grupo_conta WHERE nome = :n AND id NOT IN (SELECT grupo_id FROM conta)"
        ), {'n': grupo})
