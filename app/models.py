# Local: app/models.py

from app import db
from datetime import datetime

class Produto(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False, unique=True)
    preco = db.Column(db.Float, nullable=False)
    custo = db.Column(db.Float, nullable=False, default=0.0)
    quantidade = db.Column(db.Integer, nullable=False, default=0)
    estoque_minimo = db.Column(db.Integer, nullable=False, default=0)

    def __repr__(self):
        return f'<Produto {self.nome}>'

class Venda(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    data = db.Column(db.DateTime, nullable=False)
    total = db.Column(db.Float, nullable=False)
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
