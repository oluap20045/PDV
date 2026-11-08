"""Importação de compra a partir da NFC-e: casa itens da nota com produtos e grava tudo."""
import difflib
import math
import re
import unicodedata
from datetime import datetime

from flask import current_app
from itsdangerous import BadSignature, URLSafeSerializer

from app import db
from app.precificacao import registrar_entrada
from app.models import (Compra, CompraItem, Conta, Fornecedor, Lancamento, Produto,
                        ProdutoVinculoNfce)

LIMIAR_PARECIDO = 0.82


def normalizar(texto):
    sem_acento = unicodedata.normalize('NFKD', texto or '').encode('ascii', 'ignore').decode()
    return re.sub(r'\s+', ' ', sem_acento).strip().upper()


def _serializer():
    return URLSafeSerializer(current_app.config['SECRET_KEY'], salt='nfce-compra')


def assinar(dados):
    return _serializer().dumps(dados)


def ler_assinado(token):
    try:
        return _serializer().loads(token)
    except BadSignature:
        return None


def quantidade_inteira(qtd):
    """Estoque é em unidades inteiras: 2.0 -> 2; 0.35 kg -> 1 (o usuário ajusta na tela)."""
    return max(1, int(round(qtd))) if qtd and abs(qtd - round(qtd)) < 1e-6 else max(1, math.ceil(qtd or 1))


def casar_item(item, cnpj, produtos, por_nome):
    """Procura um produto já cadastrado para o item da nota. Devolve (produto, motivo, confiavel)."""
    desc = normalizar(item['descricao'])
    codigo = item.get('codigo') or ''

    # 1. já importado antes desta mesma loja (código da loja)
    if cnpj and codigo:
        v = ProdutoVinculoNfce.query.filter_by(cnpj=cnpj, codigo=codigo).first()
        if v:
            return v.produto, 'já comprado antes nesta loja', True
    # 2. código da nota é o código de barras de um produto
    if len(codigo) >= 8:
        p = Produto.query.filter_by(codigo_barras=codigo).first()
        if p:
            return p, 'mesmo código de barras', True
    # 3. mesma descrição já vinculada (outra loja)
    v = ProdutoVinculoNfce.query.filter_by(descricao=desc).first()
    if v:
        return v.produto, 'já comprado antes (outra loja)', True
    # 4. mesmo nome
    if desc in por_nome:
        return por_nome[desc], 'mesmo nome', True
    # 5. nome parecido: sugere, mas pede conferência
    # (a) parecido letra a letra; (b) todas as palavras do nome cadastrado aparecem na nota
    #     — a descrição da nota costuma ser bem mais longa ("ADESIVOS DECORATIVOS DE PVC 21X9 C/...")
    palavras_nota = set(re.findall(r'\w+', desc))
    melhor, nota = None, 0
    for p in produtos:
        nome = normalizar(p.nome)
        r = difflib.SequenceMatcher(None, desc, nome).ratio()
        palavras = {w for w in re.findall(r'\w+', nome) if len(w) > 1}
        if len(palavras) >= 2 and palavras <= palavras_nota:
            r = max(r, 0.9)
        if r > nota:
            melhor, nota = p, r
    if melhor and nota >= LIMIAR_PARECIDO:
        return melhor, f'nome parecido ({int(nota * 100)}%) — confira', False
    return None, None, False


def preparar_previa(dados):
    """Acrescenta à nota lida: casamento de produtos, fornecedor e duplicidade."""
    produtos = Produto.query.order_by(Produto.nome).all()
    por_nome = {normalizar(p.nome): p for p in produtos}
    cnpj = dados.get('cnpj') or ''

    for it in dados['itens']:
        produto, motivo, confiavel = casar_item(it, cnpj, produtos, por_nome)
        it['produto_id'] = produto.id if produto else None
        it['produto_nome'] = produto.nome if produto else None
        it['motivo'] = motivo
        it['confiavel'] = confiavel
        it['qtd_estoque'] = quantidade_inteira(it['quantidade'])
        it['nome_sugerido'] = it['descricao'].title()[:100]

    fornecedor = None
    if cnpj:
        fornecedor = Fornecedor.query.filter_by(cnpj=cnpj).first()
    if not fornecedor:
        fornecedor = Fornecedor.query.filter(db.func.upper(Fornecedor.nome) == dados['estabelecimento'].upper()).first()
    dados['fornecedor_existente'] = fornecedor.nome if fornecedor else None

    dados['compra_existente'] = None
    if dados.get('chave_acesso'):
        c = Compra.query.filter_by(chave_acesso=dados['chave_acesso']).first()
        if c:
            dados['compra_existente'] = {'id': c.id, 'data': c.data_compra.strftime('%d/%m/%Y'),
                                         'valor': c.valor_total}
    return dados


def _fornecedor(dados):
    cnpj = dados.get('cnpj') or None
    f = Fornecedor.query.filter_by(cnpj=cnpj).first() if cnpj else None
    if not f:
        f = Fornecedor.query.filter(db.func.upper(Fornecedor.nome) == dados['estabelecimento'].upper()).first()
        if f and cnpj and not f.cnpj:
            f.cnpj = cnpj
    if not f:
        f = Fornecedor(nome=dados['estabelecimento'][:150], cnpj=cnpj)
        db.session.add(f)
        db.session.flush()
    return f


def confirmar(dados, form, agora):
    """Grava fornecedor, produtos novos, compra, itens, estoque, vínculos e o lançamento a pagar.
    Levanta ValueError com mensagem amigável se algo não fecha."""
    if dados.get('chave_acesso') and Compra.query.filter_by(chave_acesso=dados['chave_acesso']).first():
        raise ValueError('Esta nota já foi importada antes.')

    conta = db.session.get(Conta, form.get('conta_id', type=int) or 0)
    if conta is None:
        raise ValueError('Escolha a conta de despesa.')

    data_compra = datetime.fromisoformat(dados['data_compra']) if dados.get('data_compra') else agora
    pago = form.get('pago') == '1'
    try:
        vencimento = datetime.strptime(form.get('data_vencimento', ''), '%Y-%m-%d').date()
    except ValueError:
        vencimento = data_compra.date()

    fornecedor = _fornecedor(dados)
    compra = Compra(
        nota_fiscal=dados.get('numero') or '', data_compra=data_compra, data_vencimento=vencimento,
        fornecedor_id=fornecedor.id, chave_acesso=dados.get('chave_acesso'), valor_total=dados['valor_total'],
    )
    db.session.add(compra)

    cnpj = dados.get('cnpj') or ''
    entraram = 0
    for i, it in enumerate(dados['itens']):
        acao = form.get(f'acao_{i}', 'ignorar')
        if acao == 'ignorar':
            continue
        qtd = form.get(f'qtd_{i}', type=int) or 0
        if qtd <= 0:
            raise ValueError(f'Quantidade inválida em "{it["descricao"]}".')
        custo_unit = round(it['custo_total'] / qtd, 4)

        if acao == 'novo':
            nome = (form.get(f'nome_{i}') or '').strip()[:100]
            preco = form.get(f'preco_{i}', type=float)
            if not nome or not preco or preco <= 0:
                raise ValueError(f'Informe nome e preço de venda do novo produto "{it["descricao"]}".')
            existente = Produto.query.filter(db.func.upper(Produto.nome) == nome.upper()).first()
            if existente:   # o usuário digitou um nome que já existe: usa o produto em vez de duplicar
                produto = existente
            else:
                codigo = it.get('codigo') if len(it.get('codigo') or '') >= 8 else None
                if codigo and Produto.query.filter_by(codigo_barras=codigo).first():
                    codigo = None
                produto = Produto(nome=nome, preco=preco, custo=custo_unit, quantidade=0,
                                  estoque_minimo=0, codigo_barras=codigo)
                db.session.add(produto)
                db.session.flush()
        elif acao.startswith('p:'):
            produto = db.session.get(Produto, int(acao[2:]))
            if produto is None:
                raise ValueError('Produto escolhido não existe mais; recarregue a nota.')
        else:
            continue

        registrar_entrada(produto, qtd, custo_unit)   # estoque + custo médio ponderado
        db.session.add(CompraItem(compra=compra, produto_id=produto.id, quantidade=qtd, custo_unitario=custo_unit))
        entraram += 1

        # aprende o vínculo para as próximas notas
        desc = normalizar(it['descricao'])[:200]
        codigo = (it.get('codigo') or '')[:60]
        v = ProdutoVinculoNfce.query.filter_by(cnpj=cnpj, codigo=codigo, descricao=desc).first()
        if v:
            v.produto_id = produto.id
        else:
            db.session.add(ProdutoVinculoNfce(cnpj=cnpj, codigo=codigo, descricao=desc, produto_id=produto.id))

    forma = dados.get('forma_pagamento') or ''
    lanc = Lancamento(
        descricao=(f'Compra NFC-e {dados.get("numero") or "s/n"} - {fornecedor.nome}'
                   + (f' ({forma})' if forma else ''))[:200],
        valor=dados['valor_total'], tipo='PAGAR', data_lancamento=agora, data_vencimento=vencimento,
        data_pagamento=(data_compra if pago else None), conta_id=conta.id,
    )
    db.session.add(lanc)
    db.session.flush()
    compra.lancamento_id = lanc.id
    db.session.commit()
    return compra, entraram, pago
