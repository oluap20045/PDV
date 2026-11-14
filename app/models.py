# Local: app/models.py

import hashlib
import json
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from app import db

NOME_CLIENTE_PADRAO = 'Consumidor final'
NOME_CONTA_VENDAS = 'Venda de Produtos'
NOME_CONTA_TAXAS = 'Taxas de Cartão/Maquininha'
FORMA_PIX, FORMA_DINHEIRO, FORMA_DEBITO, FORMA_CREDITO, FORMA_A_PRAZO = (
    'Pix', 'Dinheiro', 'Cartão de débito', 'Cartão de crédito', 'Fiado')
FORMAS_PAGAMENTO = [FORMA_PIX, FORMA_DINHEIRO, FORMA_DEBITO, FORMA_CREDITO, FORMA_A_PRAZO]
FORMAS_CARTAO = [FORMA_DEBITO, FORMA_CREDITO]           # pedem bandeira
BANDEIRAS = ['Visa', 'Mastercard', 'Elo', 'American Express', 'Hipercard', 'Cabal', 'Diners', 'Outra']
MAX_PARCELAS = 12

class Produto(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False, unique=True)
    preco = db.Column(db.Float, nullable=False)
    custo = db.Column(db.Float, nullable=False, default=0.0)
    quantidade = db.Column(db.Integer, nullable=False, default=0)
    estoque_minimo = db.Column(db.Integer, nullable=False, default=0)
    codigo_barras = db.Column(db.String(50), unique=True, nullable=True, index=True)
    codigo_fornecedor = db.Column(db.String(20), unique=True, nullable=True)   # ex.: código Cacau Show do catálogo
    categoria = db.Column(db.String(60), nullable=True)
    na_loja = db.Column(db.Boolean, nullable=False, default=True)    # aparece na loja online (se tiver estoque livre)
    descricao = db.Column(db.String(300), nullable=True)             # texto curto na loja online
    foto = db.relationship('ProdutoFoto', uselist=False, lazy=True, cascade='all, delete-orphan')

    def __repr__(self):
        return f'<Produto {self.nome}>'


class ProdutoFoto(db.Model):
    """Foto do produto para a loja online. Fica no banco (entra no backup diário junto com o resto)."""
    __tablename__ = 'produto_foto'
    produto_id = db.Column(db.Integer, db.ForeignKey('produto.id'), primary_key=True)
    dados = db.Column(db.LargeBinary(length=4 * 1024 * 1024), nullable=False)   # MEDIUMBLOB no MariaDB
    mime = db.Column(db.String(20), nullable=False)
    atualizado_em = db.Column(db.DateTime, nullable=False, default=datetime.now)

    @property
    def versao(self):
        return int(self.atualizado_em.timestamp())

class Venda(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    data = db.Column(db.DateTime, nullable=False)
    total = db.Column(db.Float, nullable=False)
    cliente_id = db.Column(db.Integer, db.ForeignKey('cliente.id'), nullable=False, index=True)
    forma_pagamento = db.Column(db.String(120), nullable=False, default='Dinheiro')   # resumo: "Pix + Crédito Visa 3x"
    taxa_total = db.Column(db.Float, nullable=False, default=0.0)   # taxas de cartão (custo da venda)
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuario.id'), nullable=True, index=True)   # quem vendeu
    usuario = db.relationship('Usuario')
    pagamentos = db.relationship('VendaPagamento', backref='venda', lazy=True, cascade='all, delete-orphan',
                                 order_by='VendaPagamento.id')
    itens = db.relationship('ItemVenda', backref='venda', lazy=True)

class ItemVenda(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    venda_id = db.Column(db.Integer, db.ForeignKey('venda.id'), nullable=False)
    produto_id = db.Column(db.Integer, db.ForeignKey('produto.id'), nullable=False)
    quantidade = db.Column(db.Integer, nullable=False)
    preco_unitario = db.Column(db.Float, nullable=False)
    custo_unitario = db.Column(db.Float, nullable=False)
    preco_tabela = db.Column(db.Float, nullable=True)   # preço do cadastro na hora; diferente de preco_unitario = desconto
    combo_id = db.Column(db.Integer, db.ForeignKey('combo.id'), nullable=True, index=True)   # vendido dentro de um combo
    combo_grupo = db.Column(db.SmallInteger, nullable=True)   # nº do combo na venda (2 combos iguais = grupos 1 e 2)

    produto = db.relationship('Produto')
    combo = db.relationship('Combo')
class GrupoConta(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(50), nullable=False, unique=True)
    contas = db.relationship('Conta', backref='grupo', lazy=True)

    def __repr__(self):
        return f'<GrupoConta {self.nome}>'

class Conta(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False, unique=True)
    grupo_id = db.Column(db.Integer, db.ForeignKey('grupo_conta.id'), nullable=False)
    lancamentos = db.relationship('Lancamento', backref='conta', lazy=True)

    def __repr__(self):
        return f'<Conta {self.nome}>'

class Lancamento(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    descricao = db.Column(db.String(200), nullable=False)
    valor = db.Column(db.Float, nullable=False)
    tipo = db.Column(db.String(10), nullable=False) # 'PAGAR' ou 'RECEBER'
    
    data_lancamento = db.Column(db.DateTime, nullable=False)
    data_vencimento = db.Column(db.Date, nullable=False)
    data_pagamento = db.Column(db.DateTime, nullable=True) # Pode ser nulo se não foi pago

    conta_id = db.Column(db.Integer, db.ForeignKey('conta.id'), nullable=False)

    def __repr__(self):
        return f'<Lancamento {self.descricao}>'


class Fornecedor(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(150), nullable=False, unique=True)
    cnpj = db.Column(db.String(14), unique=True, nullable=True)   # só dígitos; preenchido na importação de NFC-e
    contato = db.Column(db.String(100), nullable=True)      # nome de quem atende (vendedor, consultora)
    whatsapp = db.Column(db.String(20), nullable=True)      # só dígitos, com DDD — para mandar a ordem de compra
    compras = db.relationship('Compra', backref='fornecedor', lazy=True)

    def __repr__(self):
        return f'<Fornecedor {self.nome}>'

class Compra(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nota_fiscal = db.Column(db.String(50), nullable=True)
    data_compra = db.Column(db.DateTime, nullable=False)
    data_vencimento = db.Column(db.Date, nullable=False)
    valor_total = db.Column(db.Float, nullable=False, default=0.0)
    
    fornecedor_id = db.Column(db.Integer, db.ForeignKey('fornecedor.id'), nullable=False)
    lancamento_id = db.Column(db.Integer, db.ForeignKey('lancamento.id'), nullable=True) # Link com o contas a pagar
    chave_acesso = db.Column(db.String(44), unique=True, nullable=True)  # NFC-e importada (barra reimportação)
    
    itens = db.relationship('CompraItem', backref='compra', lazy=True, cascade="all, delete-orphan")

class CompraItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    quantidade = db.Column(db.Integer, nullable=False)
    custo_unitario = db.Column(db.Float, nullable=False)
    
    compra_id = db.Column(db.Integer, db.ForeignKey('compra.id'), nullable=False)
    produto_id = db.Column(db.Integer, db.ForeignKey('produto.id'), nullable=False)
    
    produto = db.relationship('Produto')


class Cliente(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(150), nullable=False)
    telefone = db.Column(db.String(20))
    whatsapp = db.Column(db.String(20))
    email = db.Column(db.String(150))
    cpf = db.Column(db.String(11), unique=True, index=True)   # só dígitos
    bloco = db.Column(db.String(6), nullable=True)            # "1", "A" (sem a palavra "bloco")
    apartamento = db.Column(db.String(8), nullable=True)      # "34", "101B"
    origem = db.Column(db.String(12), nullable=True)          # como chegou: balcao | loja | sorteio
    criado_em = db.Column(db.DateTime, nullable=False, default=datetime.now)
    padrao = db.Column(db.Boolean, nullable=False, default=False)   # "Consumidor final", pré-selecionado no PDV
    vendas = db.relationship('Venda', backref='cliente', lazy=True)

    @classmethod
    def padrao_do_sistema(cls):
        cliente = cls.query.filter_by(padrao=True).first()
        if cliente is None:   # garantia: se alguém apagar direto no banco, recria
            cliente = cls(nome=NOME_CLIENTE_PADRAO, padrao=True)
            db.session.add(cliente)
            db.session.commit()
        return cliente

    __table_args__ = (db.Index('ix_cliente_bloco_apto', 'bloco', 'apartamento'),)

    @property
    def endereco(self):
        """'Bl 1 · ap 34' (vazio se não tiver)."""
        return ' · '.join(filter(None, [f'Bl {self.bloco}' if self.bloco else '',
                                        f'ap {self.apartamento}' if self.apartamento else '']))

    def __repr__(self):
        return f'<Cliente {self.nome}>'


class ProdutoVinculoNfce(db.Model):
    """Memória da importação de NFC-e: 'o item X da loja Y é o produto Z'.
    Na próxima nota da mesma loja (ou com a mesma descrição) o produto já vem casado."""
    __tablename__ = 'produto_vinculo_nfce'
    id = db.Column(db.Integer, primary_key=True)
    cnpj = db.Column(db.String(14), nullable=False, default='')
    codigo = db.Column(db.String(60), nullable=False, default='')
    descricao = db.Column(db.String(200), nullable=False, index=True)   # normalizada (sem acento, maiúscula)
    produto_id = db.Column(db.Integer, db.ForeignKey('produto.id'), nullable=False)
    produto = db.relationship('Produto')
    __table_args__ = (db.UniqueConstraint('cnpj', 'codigo', 'descricao', name='uq_vinculo_nfce'),)


class TaxaPagamento(db.Model):
    """Taxa cobrada pela maquininha. bandeira NULL = vale para qualquer bandeira (usada se não houver uma específica).
    Débito/Pix/crédito à vista: parcelas 1..1. Parcelado: faixa (ex.: 2..6)."""
    __tablename__ = 'taxa_pagamento'
    id = db.Column(db.Integer, primary_key=True)
    forma = db.Column(db.String(30), nullable=False)
    bandeira = db.Column(db.String(30), nullable=True)
    parcelas_de = db.Column(db.Integer, nullable=False, default=1)
    parcelas_ate = db.Column(db.Integer, nullable=False, default=1)
    percentual = db.Column(db.Float, nullable=False)

    @property
    def modalidade(self):
        if self.forma == FORMA_CREDITO:
            if self.parcelas_ate <= 1:
                return 'Crédito à vista'
            return f'Crédito parcelado {self.parcelas_de}x a {self.parcelas_ate}x'
        return 'Débito' if self.forma == FORMA_DEBITO else self.forma

    @classmethod
    def buscar(cls, forma, bandeira, parcelas):
        """Taxa mais específica: a da bandeira; senão a de 'qualquer bandeira'. None se não houver."""
        base = cls.query.filter(cls.forma == forma, cls.parcelas_de <= parcelas, cls.parcelas_ate >= parcelas)
        if bandeira:
            taxa = base.filter(cls.bandeira == bandeira).first()
            if taxa:
                return taxa
        return base.filter(cls.bandeira.is_(None)).first()


class VendaPagamento(db.Model):
    """Uma das formas de pagamento de uma venda (a venda pode ter várias)."""
    __tablename__ = 'venda_pagamento'
    id = db.Column(db.Integer, primary_key=True)
    venda_id = db.Column(db.Integer, db.ForeignKey('venda.id'), nullable=False, index=True)
    forma = db.Column(db.String(30), nullable=False)
    bandeira = db.Column(db.String(30), nullable=True)
    parcelas = db.Column(db.Integer, nullable=False, default=1)
    valor = db.Column(db.Float, nullable=False)
    taxa_percentual = db.Column(db.Float, nullable=False, default=0.0)
    taxa_valor = db.Column(db.Float, nullable=False, default=0.0)
    lancamento_id = db.Column(db.Integer, db.ForeignKey('lancamento.id'), nullable=True)        # a receber
    lancamento_taxa_id = db.Column(db.Integer, db.ForeignKey('lancamento.id'), nullable=True)   # despesa da taxa
    lancamento = db.relationship('Lancamento', foreign_keys=[lancamento_id])
    lancamento_taxa = db.relationship('Lancamento', foreign_keys=[lancamento_taxa_id])

    @property
    def descricao(self):
        if self.forma == FORMA_CREDITO:
            return f'Crédito {self.bandeira or ""} {self.parcelas}x'.replace('  ', ' ') if self.parcelas > 1 \
                else f'Crédito {self.bandeira or ""} à vista'.replace('  ', ' ')
        if self.forma == FORMA_DEBITO:
            return f'Débito {self.bandeira or ""}'.strip()
        return self.forma


SEMANA_PADRAO = json.dumps([['18:00', '23:00']] * 7)


class Empresa(db.Model):
    """Dados do cabeçalho do comprovante (uma linha só)."""
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(120), nullable=False, default='Minha Empresa')
    cnpj = db.Column(db.String(14))
    telefone = db.Column(db.String(20))
    endereco = db.Column(db.String(200))
    mensagem = db.Column(db.String(200), default='Obrigado pela preferência!')
    margem_lucro = db.Column(db.Float, nullable=False, default=30.0)   # % do preço, usada na sugestão de preço
    cadastro_aberto = db.Column(db.Boolean, nullable=False, default=True)   # "Criar conta" na tela de login
    saldo_inicial = db.Column(db.Float, nullable=False, default=0.0)   # dinheiro em caixa/banco antes dos lançamentos
    prazo_cartao = db.Column(db.Integer, nullable=False, default=1)    # D+N: dias até a maquininha depositar
    # loja online (/loja)
    # auto = abre/fecha sozinha no horário; aberta / fechada = manual, até mudar de novo
    loja_modo = db.Column(db.String(10), nullable=False, default='fechada')
    # horário de cada dia da semana (0=segunda … 6=domingo): JSON [["18:00","23:00"], null (fechado), ...]
    # fecha antes de abrir = vira a meia-noite (ex.: 20:00 às 02:00)
    loja_semana = db.Column(db.String(200), nullable=False, default=SEMANA_PADRAO)
    loja_aviso = db.Column(db.String(300), nullable=True)      # recado no topo da loja ("entregas sáb. à tarde")
    loja_whatsapp = db.Column(db.String(13), nullable=True)    # só dígitos com DDD; recebe o aviso de pedido novo
    pix_chave = db.Column(db.String(77), nullable=True)
    pix_nome = db.Column(db.String(25), nullable=True)         # nome do recebedor (aparece no app do banco)
    pix_cidade = db.Column(db.String(15), nullable=True)

    # ---------------------------------------------------------------- horário da loja online

    @property
    def loja_grade(self):
        """[(abre, fecha) | None] x 7, segunda a domingo."""
        try:
            dados = json.loads(self.loja_semana or '[]')
        except ValueError:
            dados = []
        grade = []
        for i in range(7):
            j = dados[i] if i < len(dados) else None
            try:
                grade.append((time.fromisoformat(j[0]), time.fromisoformat(j[1])) if j else None)
            except (TypeError, ValueError, IndexError):
                grade.append(None)
        return grade

    @loja_grade.setter
    def loja_grade(self, grade):
        self.loja_semana = json.dumps([[a.strftime('%H:%M'), f.strftime('%H:%M')] if (a and f) else None
                                       for a, f in ((j or (None, None)) for j in grade)])

    @staticmethod
    def _agora():
        return datetime.now(ZoneInfo('America/Sao_Paulo')).replace(tzinfo=None)

    def janela_em(self, momento):
        """(início, fim) em datetime do horário que cobre `momento` (inclui o de ontem que virou a meia-noite)."""
        grade = self.loja_grade
        for dias_atras in (0, 1):
            dia = momento.date() - timedelta(days=dias_atras)
            j = grade[dia.weekday()]
            if not j:
                continue
            inicio = datetime.combine(dia, j[0])
            fim = datetime.combine(dia + timedelta(days=1 if j[1] <= j[0] else 0), j[1])
            if inicio <= momento < fim:
                return inicio, fim
        return None

    def janela_do_dia(self, dia):
        j = self.loja_grade[dia.weekday()]
        if not j:
            return None
        return datetime.combine(dia, j[0]), datetime.combine(dia + timedelta(days=1 if j[1] <= j[0] else 0), j[1])

    def loja_situacao(self, agora=None):
        """(aberta_agora, próxima_abertura | None) conforme o modo e o horário."""
        agora = agora or self._agora()
        if self.loja_modo == 'aberta':
            return True, None
        if self.loja_modo != 'auto':
            return False, None
        if self.janela_em(agora):
            return True, None
        for i in range(8):
            j = self.janela_do_dia(agora.date() + timedelta(days=i))
            if j and j[0] > agora:
                return False, j[0]
        return False, None

    @staticmethod
    def _hora(t):
        return t.strftime('%H:%M')

    def horario_texto(self, momento=None):
        """'18:00 às 23:00' do horário em que `momento` cai (ou o do dia), para "Entregas das ..."."""
        momento = momento or self._agora()
        j = self.janela_em(momento) or self.janela_do_dia(momento.date())
        return f'{self._hora(j[0])} às {self._hora(j[1])}' if j else None

    def horario_agora(self, agora=None):
        """Horário de entrega que ainda vale hoje (o de agora ou o que vai começar); None se o de hoje já acabou."""
        agora = agora or self._agora()
        j = self.janela_em(agora) or self.janela_do_dia(agora.date())
        return f'{self._hora(j[0])} às {self._hora(j[1])}' if j and j[1] > agora else None

    def horario_semana(self, hoje=None):
        """[{'dias': 'Seg a Qui', 'horario': '18:00 às 23:00' | None, 'hoje': bool}] juntando dias seguidos iguais."""
        hoje = (hoje or self._agora()).weekday()
        nomes = ['Seg', 'Ter', 'Qua', 'Qui', 'Sex', 'Sáb', 'Dom']
        grade, linhas = self.loja_grade, []
        for i, j in enumerate(grade):
            texto = f'{self._hora(j[0])} às {self._hora(j[1])}' if j else None
            if linhas and linhas[-1]['horario'] == texto:
                linhas[-1]['fim'] = i
                linhas[-1]['hoje'] = linhas[-1]['hoje'] or i == hoje
            else:
                linhas.append({'inicio': i, 'fim': i, 'horario': texto, 'hoje': i == hoje})
        for l in linhas:
            a, b = l.pop('inicio'), l.pop('fim')
            l['dias'] = nomes[a] if a == b else (f'{nomes[a]} e {nomes[b]}' if b == a + 1 else f'{nomes[a]} a {nomes[b]}')
        return linhas

    @property
    def loja_aberta(self):
        return self.loja_situacao()[0]

    @classmethod
    def atual(cls):
        empresa = cls.query.first()
        if empresa is None:
            empresa = cls(nome='Minha Empresa', mensagem='Obrigado pela preferência!')
            db.session.add(empresa)
            db.session.commit()
        return empresa


class Usuario(UserMixin, db.Model):
    """Quem acessa o sistema. Senha guardada só como hash."""
    MAX_TENTATIVAS = 5
    BLOQUEIO = timedelta(minutes=5)

    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    login = db.Column(db.String(50), nullable=False, unique=True)     # sempre minúsculo
    senha_hash = db.Column(db.String(255), nullable=False)
    ativo = db.Column(db.Boolean, nullable=False, default=True)
    criado_em = db.Column(db.DateTime, nullable=False, default=datetime.now)
    ultimo_acesso = db.Column(db.DateTime)
    tentativas_falhas = db.Column(db.Integer, nullable=False, default=0)
    bloqueado_ate = db.Column(db.DateTime)

    def definir_senha(self, senha):
        self.senha_hash = generate_password_hash(senha)

    def senha_confere(self, senha):
        return check_password_hash(self.senha_hash, senha)

    @property
    def is_active(self):
        return bool(self.ativo)

    def get_id(self):
        # id + carimbo da senha: trocar a senha derruba as sessões abertas em outros aparelhos
        return f'{self.id}:{self.carimbo_senha()}'

    def carimbo_senha(self):
        return hashlib.sha256(self.senha_hash.encode()).hexdigest()[:16]

    def bloqueado(self, agora=None):
        return bool(self.bloqueado_ate and self.bloqueado_ate > (agora or datetime.now()))


# ---------------------------------------------------------------- Pedidos e ordens de compra

class Pedido(db.Model):
    """Encomenda de cliente: aceita qualquer produto, com ou sem estoque. Vira venda na entrega."""
    id = db.Column(db.Integer, primary_key=True)
    cliente_id = db.Column(db.Integer, db.ForeignKey('cliente.id'), nullable=False, index=True)
    criado_em = db.Column(db.DateTime, nullable=False, default=datetime.now)
    previsao = db.Column(db.Date, nullable=True)                  # quando o cliente quer
    observacao = db.Column(db.String(255), nullable=True)
    status = db.Column(db.String(12), nullable=False, default='aberto', index=True)   # aberto | entregue | cancelado
    venda_id = db.Column(db.Integer, db.ForeignKey('venda.id'), nullable=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuario.id'), nullable=True)
    # pedidos feitos pela loja online
    origem = db.Column(db.String(10), nullable=False, default='balcao', index=True)   # balcao | loja
    codigo = db.Column(db.String(16), nullable=True, unique=True)    # link do cliente: /loja/p/<codigo>
    entrega = db.Column(db.String(120), nullable=True)               # bloco/apto
    pagamento = db.Column(db.String(30), nullable=True)              # como o cliente disse que vai pagar
    cliente = db.relationship('Cliente')
    venda = db.relationship('Venda')
    usuario = db.relationship('Usuario')
    itens = db.relationship('PedidoItem', backref='pedido', lazy=True, cascade='all, delete-orphan',
                            order_by='PedidoItem.id')

    @property
    def total(self):
        return round(sum(i.quantidade * i.preco_unitario for i in self.itens), 2)


class PedidoItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    pedido_id = db.Column(db.Integer, db.ForeignKey('pedido.id'), nullable=False, index=True)
    produto_id = db.Column(db.Integer, db.ForeignKey('produto.id'), nullable=False)
    quantidade = db.Column(db.Integer, nullable=False)
    preco_unitario = db.Column(db.Float, nullable=False)          # preço combinado com o cliente
    combo_id = db.Column(db.Integer, db.ForeignKey('combo.id'), nullable=True)
    combo_grupo = db.Column(db.SmallInteger, nullable=True)
    produto = db.relationship('Produto')
    combo = db.relationship('Combo')


class OrdemCompra(db.Model):
    """Lista do que encomendar ao fornecedor. Ao chegar, vira uma Compra (estoque + contas a pagar)."""
    __tablename__ = 'ordem_compra'
    id = db.Column(db.Integer, primary_key=True)
    criado_em = db.Column(db.DateTime, nullable=False, default=datetime.now)
    fornecedor_id = db.Column(db.Integer, db.ForeignKey('fornecedor.id'), nullable=True)
    status = db.Column(db.String(12), nullable=False, default='aberta', index=True)   # aberta | recebida | cancelada
    compra_id = db.Column(db.Integer, db.ForeignKey('compra.id'), nullable=True)
    observacao = db.Column(db.String(255), nullable=True)
    fornecedor = db.relationship('Fornecedor')
    compra = db.relationship('Compra')
    itens = db.relationship('OrdemCompraItem', backref='ordem', lazy=True, cascade='all, delete-orphan',
                            order_by='OrdemCompraItem.id')


class OrdemCompraItem(db.Model):
    __tablename__ = 'ordem_compra_item'
    id = db.Column(db.Integer, primary_key=True)
    ordem_id = db.Column(db.Integer, db.ForeignKey('ordem_compra.id'), nullable=False, index=True)
    produto_id = db.Column(db.Integer, db.ForeignKey('produto.id'), nullable=False)
    quantidade = db.Column(db.Integer, nullable=False)
    produto = db.relationship('Produto')


# ---------------------------------------------------------------- Baixa de estoque (brinde, perda...)

MOTIVOS_BAIXA = {
    'brinde': 'Brinde',
    'degustacao': 'Degustação',
    'perda': 'Perda / avaria',
    'vencido': 'Vencido',
    'consumo': 'Consumo próprio',
    'outro': 'Outro',
}


class BaixaEstoque(db.Model):
    """Saída de estoque sem venda. Não gera lançamento financeiro (o custo já foi pago na compra):
    só tira do estoque e registra o valor a custo, para saber quanto foi em brinde, perda etc."""
    __tablename__ = 'baixa_estoque'
    id = db.Column(db.Integer, primary_key=True)
    data = db.Column(db.DateTime, nullable=False, index=True)
    produto_id = db.Column(db.Integer, db.ForeignKey('produto.id'), nullable=False, index=True)
    quantidade = db.Column(db.Integer, nullable=False)
    custo_unitario = db.Column(db.Float, nullable=False, default=0.0)   # custo médio na hora da baixa
    motivo = db.Column(db.String(20), nullable=False, index=True)      # chave de MOTIVOS_BAIXA
    observacao = db.Column(db.String(255), nullable=True)
    cliente_id = db.Column(db.Integer, db.ForeignKey('cliente.id'), nullable=True)   # brinde para quem
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuario.id'), nullable=True)
    estornada_em = db.Column(db.DateTime, nullable=True)                # desfeita: o estoque voltou
    produto = db.relationship('Produto')
    cliente = db.relationship('Cliente')
    usuario = db.relationship('Usuario')

    @property
    def valor_custo(self):
        return round(self.quantidade * (self.custo_unitario or 0), 2)

    @property
    def motivo_nome(self):
        return MOTIVOS_BAIXA.get(self.motivo, self.motivo)


class LojaEvento(db.Model):
    """Acesso/clique na loja online (analisador de tráfego). Sem dado pessoal: `visitante` é um código
    aleatório que o próprio navegador guarda (não é IP, nome nem telefone)."""
    __tablename__ = 'loja_evento'
    id = db.Column(db.BigInteger().with_variant(db.Integer, 'sqlite'), primary_key=True)
    criado_em = db.Column(db.DateTime, nullable=False, index=True)
    visitante = db.Column(db.String(24), nullable=False, index=True)
    tipo = db.Column(db.String(20), nullable=False, index=True)   # chave de TIPOS_EVENTO
    alvo = db.Column(db.String(120), nullable=True)                # categoria, produto, botão...
    produto_id = db.Column(db.Integer, nullable=True, index=True)  # sem FK: produto apagado não apaga a estatística
    pagina = db.Column(db.String(20), nullable=True)               # loja | pedido | fechada
    origem = db.Column(db.String(40), nullable=True)               # whatsapp, folder, google... ou 'direto'
    dispositivo = db.Column(db.String(12), nullable=True)          # celular | computador | tablet


TIPOS_EVENTO = {
    'visita': 'Abriu a página',
    'categoria': 'Filtrou categoria',
    'adicionar': 'Adicionou ao carrinho',
    'carrinho': 'Abriu o carrinho',
    'pedido': 'Fez pedido',
    'whatsapp': 'Clicou no WhatsApp',
    'pix': 'Copiou o Pix',
    'sorteio': 'Inscreveu no sorteio',
    'clique': 'Outro clique',
}


# ---------------------------------------------------------------- Combos / promoções ("4 por 12")

combo_produto = db.Table(
    'combo_produto',
    db.Column('combo_id', db.Integer, db.ForeignKey('combo.id', ondelete='CASCADE'), primary_key=True),
    db.Column('produto_id', db.Integer, db.ForeignKey('produto.id', ondelete='CASCADE'), primary_key=True),
)


class Combo(db.Model):
    """Leve N itens (o cliente escolhe entre os produtos do combo) por um preço fechado.
    Na venda cada unidade continua sendo do seu produto (baixa o estoque certo e guarda o custo certo);
    o preço do combo é dividido entre as unidades e as linhas ficam marcadas com combo_id/combo_grupo."""
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(80), nullable=False)
    quantidade = db.Column(db.Integer, nullable=False)          # leve N...
    preco = db.Column(db.Float, nullable=False)                 # ...por R$ X
    ativo = db.Column(db.Boolean, nullable=False, default=True)
    no_pdv = db.Column(db.Boolean, nullable=False, default=True)
    na_loja = db.Column(db.Boolean, nullable=False, default=True)
    inicio = db.Column(db.Date, nullable=True)                  # validade opcional
    fim = db.Column(db.Date, nullable=True)
    criado_em = db.Column(db.DateTime, nullable=False, default=datetime.now)
    produtos = db.relationship('Produto', secondary=combo_produto, lazy='selectin', order_by='Produto.nome')

    def valido(self, hoje):
        return bool(self.ativo and self.produtos and (self.inicio is None or self.inicio <= hoje)
                    and (self.fim is None or self.fim >= hoje))

    @property
    def promocao(self):
        """Leve 1 = preço promocional ("de R$ 39,99 por R$ 19,90"), em vez de combo."""
        return self.quantidade == 1

    @property
    def tipo(self):
        return 'Promoção' if self.promocao else 'Combo'

    @property
    def titulo(self):
        if self.promocao:
            return f'por R$ {self.preco:.2f}'.replace('.', ',')
        return f'{self.quantidade} por R$ {self.preco:.2f}'.replace('.', ',')


# ---------------------------------------------------------------- Sorteios (formulário público + lista de inscritos)

class Sorteio(db.Model):
    """Sorteio com período de inscrição. A inscrição é pública (/loja/sorteio/<codigo>) e cada inscrito
    vira (ou reaproveita) um Cliente, casado por nome + bloco + apartamento."""
    id = db.Column(db.Integer, primary_key=True)
    codigo = db.Column(db.String(16), nullable=False, unique=True)     # link público
    premio = db.Column(db.String(120), nullable=False)                 # "Barra ao Leite 100 g"
    descricao = db.Column(db.String(300), nullable=True)               # regras / recado
    produto_id = db.Column(db.Integer, db.ForeignKey('produto.id', ondelete='SET NULL'), nullable=True)  # o prêmio (foto + estoque)
    quantidade = db.Column(db.Integer, nullable=False, default=1)                                         # unidades do prêmio
    # o prêmio sai do estoque (baixa como brinde) assim que o sorteio é salvo: não dá para vender sem querer
    baixa_id = db.Column(db.Integer, db.ForeignKey('baixa_estoque.id', ondelete='SET NULL'), nullable=True)
    inicio = db.Column(db.DateTime, nullable=False)
    fim = db.Column(db.DateTime, nullable=False)
    criado_em = db.Column(db.DateTime, nullable=False, default=datetime.now)
    produto = db.relationship('Produto')
    baixa = db.relationship('BaixaEstoque')
    inscricoes = db.relationship('SorteioInscricao', backref='sorteio', lazy=True, cascade='all, delete-orphan',
                                 order_by='SorteioInscricao.id')

    def situacao(self, momento):
        """'agendado' | 'aberto' | 'encerrado' | 'sorteado'"""
        if self.ganhador:
            return 'sorteado'
        if momento < self.inicio:
            return 'agendado'
        return 'aberto' if momento < self.fim else 'encerrado'

    @property
    def sorteados(self):
        """Inscrições já sorteadas, na ordem (a última é o ganhador; as anteriores não responderam)."""
        return sorted((i for i in self.inscricoes if i.sorteado_em), key=lambda i: (i.sorteado_em, i.id))

    @property
    def ganhador(self):
        s = self.sorteados
        return s[-1] if s else None


class SorteioInscricao(db.Model):
    __tablename__ = 'sorteio_inscricao'
    id = db.Column(db.Integer, primary_key=True)
    sorteio_id = db.Column(db.Integer, db.ForeignKey('sorteio.id', ondelete='CASCADE'), nullable=False, index=True)
    cliente_id = db.Column(db.Integer, db.ForeignKey('cliente.id'), nullable=False, index=True)
    criado_em = db.Column(db.DateTime, nullable=False)
    sorteado_em = db.Column(db.DateTime, nullable=True)       # foi tirado no sorteio (o último é o ganhador)
    cliente = db.relationship('Cliente')
    __table_args__ = (db.UniqueConstraint('sorteio_id', 'cliente_id', name='uq_sorteio_cliente'),)
