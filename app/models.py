# Local: app/models.py

from app import db
from datetime import datetime

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

    def __repr__(self):
        return f'<Produto {self.nome}>'

class Venda(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    data = db.Column(db.DateTime, nullable=False)
    total = db.Column(db.Float, nullable=False)
    cliente_id = db.Column(db.Integer, db.ForeignKey('cliente.id'), nullable=False, index=True)
    forma_pagamento = db.Column(db.String(120), nullable=False, default='Dinheiro')   # resumo: "Pix + Crédito Visa 3x"
    taxa_total = db.Column(db.Float, nullable=False, default=0.0)   # taxas de cartão (custo da venda)
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

    produto = db.relationship('Produto')
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
