"""Pedidos de clientes (aceitam qualquer produto, com ou sem estoque) e ordens de compra do que falta.

Reserva de estoque: os pedidos em aberto "pegam" o estoque por ordem de prioridade — primeiro quem tem
previsão de entrega mais cedo, depois o mais antigo. O que não couber no estoque é FALTA.
Falta − o que já está encomendado em ordens de compra abertas = o que ainda precisa comprar.
"""
from collections import defaultdict
from datetime import date, datetime
from zoneinfo import ZoneInfo

import re
from urllib.parse import quote

from flask import Blueprint, render_template, request, redirect, url_for, flash, abort, Response
from flask_login import current_user

from app import db
from app.models import Pedido, PedidoItem, OrdemCompra, OrdemCompraItem, Produto, Cliente, Fornecedor, Empresa

bp = Blueprint('pedidos', __name__)

STATUS_PEDIDO = {'aberto': 'Em aberto', 'entregue': 'Entregues', 'cancelado': 'Cancelados'}


def agora():
    return datetime.now(ZoneInfo('America/Sao_Paulo')).replace(tzinfo=None)


def _prioridade(p):
    return (p.previsao or date.max, p.criado_em, p.id)


def alocar():
    """Distribui o estoque entre os pedidos em aberto.

    Devolve (pedidos_ordenados, situacao) com situacao[item.id] = (atendido, falta)."""
    pedidos = sorted(Pedido.query.filter_by(status='aberto').all(), key=_prioridade)
    livre, situacao = {}, {}
    for ped in pedidos:
        for it in ped.itens:
            if it.produto_id not in livre:
                livre[it.produto_id] = max(it.produto.quantidade or 0, 0)
            atendido = min(it.quantidade, livre[it.produto_id])
            livre[it.produto_id] -= atendido
            situacao[it.id] = (atendido, it.quantidade - atendido)
    return pedidos, situacao


def em_ordens_abertas():
    """Quantidade já encomendada (ordens de compra abertas), por produto."""
    q = (db.session.query(OrdemCompraItem.produto_id, db.func.sum(OrdemCompraItem.quantidade))
         .join(OrdemCompra).filter(OrdemCompra.status == 'aberta').group_by(OrdemCompraItem.produto_id))
    return {pid: int(qtd or 0) for pid, qtd in q}


def faltas():
    """Linhas da tela 'o que comprar': faltas dos pedidos + produtos abaixo do estoque mínimo."""
    pedidos, situacao = alocar()
    falta = defaultdict(int)
    quem = defaultdict(list)
    reservado = defaultdict(int)
    for ped in pedidos:
        for it in ped.itens:
            atendido, f = situacao[it.id]
            reservado[it.produto_id] += atendido
            if f:
                falta[it.produto_id] += f
                quem[it.produto_id].append(ped)
    encomendado = em_ordens_abertas()

    linhas = []
    for pid, f in falta.items():
        prod = db.session.get(Produto, pid)
        comprar = max(f - encomendado.get(pid, 0), 0)
        linhas.append({'produto': prod, 'motivo': 'pedido', 'falta': f, 'pedidos': quem[pid],
                       'encomendado': encomendado.get(pid, 0), 'comprar': comprar, 'marcado': comprar > 0})
    # estoque mínimo (sugestão, vem desmarcado)
    for prod in Produto.query.filter(Produto.estoque_minimo > 0).all():
        if prod.id in falta:
            continue
        livre = max(prod.quantidade, 0) - reservado.get(prod.id, 0)
        comprar = prod.estoque_minimo - livre - encomendado.get(prod.id, 0)
        if comprar > 0:
            linhas.append({'produto': prod, 'motivo': 'minimo', 'falta': 0, 'pedidos': [],
                           'encomendado': encomendado.get(prod.id, 0), 'comprar': comprar, 'marcado': False})
    linhas.sort(key=lambda l: (l['motivo'] != 'pedido', l['comprar'] == 0, l['produto'].nome))
    return linhas


def _numero(txt):
    txt = (txt or '').strip().replace('R$', '').strip()
    if ',' in txt:
        txt = txt.replace('.', '').replace(',', '.')
    return float(txt)


def _itens_do_form():
    """Lê produto_id[]/quantidade[]/preco[] do formulário; junta produtos repetidos."""
    ids, qtds, precos = (request.form.getlist(c) for c in ('produto_id', 'quantidade', 'preco'))
    itens = {}
    for pid, qtd, preco in zip(ids, qtds, precos):
        if not pid:
            continue
        prod = db.session.get(Produto, int(pid))
        if prod is None:
            raise ValueError('Produto não encontrado.')
        try:
            q = int(qtd)
        except ValueError:
            raise ValueError(f'Quantidade inválida em {prod.nome}.')
        if q <= 0:
            raise ValueError(f'Quantidade inválida em {prod.nome}.')
        try:
            v = _numero(preco) if (preco or '').strip() else prod.preco
        except ValueError:
            raise ValueError(f'Preço inválido em {prod.nome}.')
        if v < 0:
            raise ValueError(f'Preço inválido em {prod.nome}.')
        if pid in itens:
            itens[pid]['quantidade'] += q
        else:
            itens[pid] = {'produto': prod, 'quantidade': q, 'preco': round(v, 2)}
    if not itens:
        raise ValueError('Inclua pelo menos um produto.')
    return list(itens.values())


# ---------------------------------------------------------------- Pedidos

@bp.route('/pedidos')
def pedidos():
    status = request.args.get('status', 'aberto')
    if status not in STATUS_PEDIDO:
        status = 'aberto'
    abertos, situacao = alocar()
    if status == 'aberto':
        lista = abertos
    else:
        lista = (Pedido.query.filter_by(status=status).order_by(Pedido.criado_em.desc()).limit(100).all())
    contagem = dict(db.session.query(Pedido.status, db.func.count(Pedido.id)).group_by(Pedido.status).all())
    return render_template('pedidos.html', pedidos=lista, situacao=situacao, status=status,
                           STATUS=STATUS_PEDIDO, contagem=contagem, hoje=agora().date())


def _form_pedido(pedido):
    if request.method == 'POST':
        try:
            cliente = db.session.get(Cliente, request.form.get('cliente_id', type=int) or 0)
            if cliente is None:
                raise ValueError('Escolha o cliente.')
            itens = _itens_do_form()
            prev = request.form.get('previsao') or None
            previsao = datetime.strptime(prev, '%Y-%m-%d').date() if prev else None
        except ValueError as e:
            flash(str(e), 'danger')
            return _tela_pedido(pedido, request.form)
        novo = pedido is None
        if novo:
            pedido = Pedido(criado_em=agora(), usuario_id=current_user.id)
            db.session.add(pedido)
        pedido.cliente_id = cliente.id
        pedido.previsao = previsao
        pedido.observacao = (request.form.get('observacao') or '').strip()[:255] or None
        pedido.itens.clear()
        for i in itens:
            pedido.itens.append(PedidoItem(produto_id=i['produto'].id, quantidade=i['quantidade'],
                                           preco_unitario=i['preco']))
        db.session.commit()
        _, situacao = alocar()
        faltando = sum(situacao.get(it.id, (0, 0))[1] for it in pedido.itens)
        msg = f'Pedido #{pedido.id} de {cliente.nome} {"registrado" if novo else "atualizado"} (R$ {pedido.total:.2f}).'
        msg += (f' Faltam {faltando} unidade(s) no estoque: veja em Ordens de compra.' if faltando
                else ' Tudo em estoque: pronto para entregar.')
        flash(msg, 'warning' if faltando else 'success')
        return redirect(url_for('pedidos.pedidos'))
    return _tela_pedido(pedido)


def _tela_pedido(pedido, form=None):
    produtos = Produto.query.order_by(Produto.nome).all()
    clientes = Cliente.query.order_by(Cliente.padrao.desc(), Cliente.nome).all()
    codigos = {}
    for p in produtos:
        for c in (p.codigo_barras, p.codigo_fornecedor):
            if c and c.strip():
                codigos.setdefault(c.strip(), p.id)
    if form is not None:           # erro de validação: devolve o que foi digitado
        itens = [{'produto_id': int(pid) if pid else None, 'quantidade': q, 'preco': v}
                 for pid, q, v in zip(form.getlist('produto_id'), form.getlist('quantidade'), form.getlist('preco'))]
        dados = {'cliente_id': form.get('cliente_id', type=int), 'previsao': form.get('previsao') or '',
                 'observacao': form.get('observacao') or ''}
    elif pedido is not None:
        itens = [{'produto_id': it.produto_id, 'quantidade': it.quantidade,
                  'preco': f'{it.preco_unitario:.2f}'.replace('.', ',')} for it in pedido.itens]
        dados = {'cliente_id': pedido.cliente_id, 'previsao': pedido.previsao.isoformat() if pedido.previsao else '',
                 'observacao': pedido.observacao or ''}
    else:
        itens = []
        dados = {'cliente_id': request.args.get('cliente', type=int), 'previsao': '', 'observacao': ''}
    produtos_js = {p.id: {'nome': p.nome, 'preco': p.preco, 'estoque': p.quantidade,
                          'codigo': p.codigo_fornecedor or p.codigo_barras or ''} for p in produtos}
    return render_template('pedido_form.html', pedido=pedido, produtos=produtos, clientes=clientes,
                           codigos=codigos, produtos_js=produtos_js, itens=itens, dados=dados)


@bp.route('/pedido/novo', methods=['GET', 'POST'])
def novo_pedido():
    return _form_pedido(None)


@bp.route('/pedido/<int:id>/editar', methods=['GET', 'POST'])
def editar_pedido(id):
    pedido = db.get_or_404(Pedido, id)
    if pedido.status != 'aberto':
        flash('Só dá para alterar pedido em aberto.', 'warning')
        return redirect(url_for('pedidos.pedidos', status=pedido.status))
    return _form_pedido(pedido)


@bp.route('/pedido/<int:id>/cancelar', methods=['POST'])
def cancelar_pedido(id):
    pedido = db.get_or_404(Pedido, id)
    if pedido.status == 'aberto':
        pedido.status = 'cancelado'
        db.session.commit()
        flash(f'Pedido #{pedido.id} cancelado. O estoque reservado para ele foi liberado.', 'info')
    return redirect(url_for('pedidos.pedidos'))


@bp.route('/pedido/<int:id>/reabrir', methods=['POST'])
def reabrir_pedido(id):
    pedido = db.get_or_404(Pedido, id)
    if pedido.status == 'cancelado':
        pedido.status = 'aberto'
        db.session.commit()
        flash(f'Pedido #{pedido.id} reaberto.', 'info')
    return redirect(url_for('pedidos.pedidos'))


# ---------------------------------------------------------------- Ordens de compra

@bp.route('/ordens-compra')
def ordens_compra():
    abertas = OrdemCompra.query.filter_by(status='aberta').order_by(OrdemCompra.criado_em.desc()).all()
    fechadas = (OrdemCompra.query.filter(OrdemCompra.status != 'aberta')
                .order_by(OrdemCompra.criado_em.desc()).limit(20).all())
    return render_template('ordens_compra.html', linhas=faltas(), abertas=abertas, fechadas=fechadas,
                           fornecedores=Fornecedor.query.order_by(Fornecedor.nome).all())


@bp.route('/ordens-compra/gerar', methods=['POST'])
def gerar_ordem():
    itens = []
    for pid in request.form.getlist('marcado'):
        prod = db.session.get(Produto, int(pid))
        q = request.form.get(f'qtd_{pid}', type=int) or 0
        if prod and q > 0:
            itens.append((prod, q))
    if not itens:
        flash('Marque pelo menos um produto com quantidade.', 'warning')
        return redirect(url_for('pedidos.ordens_compra'))
    ordem = OrdemCompra(criado_em=agora(), fornecedor_id=request.form.get('fornecedor_id', type=int) or None,
                        observacao=(request.form.get('observacao') or '').strip()[:255] or None)
    for prod, q in itens:
        ordem.itens.append(OrdemCompraItem(produto_id=prod.id, quantidade=q))
    db.session.add(ordem)
    db.session.commit()
    flash(f'Ordem de compra #{ordem.id} criada com {len(itens)} produto(s). '
          'Copie a lista para o fornecedor; quando chegar, clique em "Receber".', 'success')
    return redirect(url_for('pedidos.ordens_compra', _anchor=f'oc-{ordem.id}'))


@bp.route('/ordem-compra/<int:id>/cancelar', methods=['POST'])
def cancelar_ordem(id):
    ordem = db.get_or_404(OrdemCompra, id)
    if ordem.status == 'aberta':
        ordem.status = 'cancelada'
        db.session.commit()
        flash(f'Ordem de compra #{ordem.id} cancelada: os itens voltam para a lista do que comprar.', 'info')
    return redirect(url_for('pedidos.ordens_compra'))


@bp.route('/ordem-compra/<int:id>/recebida', methods=['POST'])
def marcar_recebida(id):
    """Para quando a mercadoria entrou por outro caminho (ex.: cupom NFC-e importado)."""
    ordem = db.get_or_404(OrdemCompra, id)
    if ordem.status == 'aberta':
        ordem.status = 'recebida'
        db.session.commit()
        flash(f'Ordem de compra #{ordem.id} marcada como recebida.', 'info')
    return redirect(url_for('pedidos.ordens_compra'))


@bp.route('/ordem-compra/<int:id>/fornecedor', methods=['POST'])
def trocar_fornecedor(id):
    ordem = db.get_or_404(OrdemCompra, id)
    ordem.fornecedor_id = request.form.get('fornecedor_id', type=int) or None
    db.session.commit()
    return redirect(url_for('pedidos.ordens_compra', _anchor=f'oc-{ordem.id}'))


@bp.route('/ordem-compra/<int:id>.pdf')
def ordem_pdf(id):
    from app.comprovante import gerar_pdf_ordem
    ordem = db.get_or_404(OrdemCompra, id)
    pdf = gerar_pdf_ordem(ordem, Empresa.atual())
    disposicao = 'attachment' if request.args.get('baixar') else 'inline'
    return Response(pdf, mimetype='application/pdf',
                    headers={'Content-Disposition': f'{disposicao}; filename="pedido-de-compra-{ordem.id}.pdf"'})


@bp.route('/ordem-compra/<int:id>/whatsapp')
def ordem_whatsapp(id):
    """Abre o WhatsApp na conversa do fornecedor (se tiver número) com a lista do pedido."""
    from app.comprovante import texto_whatsapp_ordem
    ordem = db.get_or_404(OrdemCompra, id)
    texto = quote(texto_whatsapp_ordem(ordem, Empresa.atual()))
    numero = re.sub(r'\D', '', (ordem.fornecedor.whatsapp or '') if ordem.fornecedor else '')
    if len(numero) in (10, 11):
        return redirect(f'https://wa.me/55{numero}?text={texto}')
    return redirect(f'https://wa.me/?text={texto}')   # sem número: o WhatsApp pede o contato


def ordem_para_compra(ordem_id):
    """Dados para pré-preencher a compra manual a partir de uma ordem aberta (ou None)."""
    ordem = db.session.get(OrdemCompra, ordem_id or 0)
    if ordem is None or ordem.status != 'aberta':
        return None
    return {'id': ordem.id, 'fornecedor_id': ordem.fornecedor_id,
            'itens': [{'produto_id': it.produto_id, 'codigo': it.produto.codigo_fornecedor or it.produto.codigo_barras or '',
                       'quantidade': it.quantidade, 'custo': round(it.produto.custo or 0, 2)} for it in ordem.itens]}


def baixar_ordem(ordem_id, compra):
    ordem = db.session.get(OrdemCompra, ordem_id or 0)
    if ordem is not None and ordem.status == 'aberta':
        ordem.status = 'recebida'
        ordem.compra_id = compra.id
