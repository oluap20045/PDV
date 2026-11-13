"""Loja online do condomínio.

`bp` (/loja/...) é PÚBLICO: catálogo, carrinho, pedido e a página do pedido do cliente.
`bp_admin` (/loja-admin/...) exige login como o resto do sistema: configuração, fotos e o que aparece.

O pedido da loja é um Pedido normal (origem='loja'): reserva estoque, aparece em Pedidos
e é entregue/cobrado pelo PDV como qualquer outro.
"""
import re
import secrets
import time
from collections import defaultdict, deque
from datetime import datetime
from urllib.parse import quote

from flask import Blueprint, Response, abort, flash, jsonify, redirect, render_template, request, url_for

from app import db
from app.models import Cliente, Empresa, Pedido, PedidoItem, Produto, ProdutoFoto
from app.pedidos import agora, alocar
from app import pix

bp = Blueprint('loja', __name__, url_prefix='/loja')
bp_admin = Blueprint('loja_admin', __name__, url_prefix='/loja-admin')

PAGAMENTOS = ['Pix', 'Dinheiro na entrega', 'Cartão na entrega']
STATUS_CLIENTE = {'aberto': 'Recebido — em preparação', 'entregue': 'Entregue', 'cancelado': 'Cancelado'}
MAX_POR_ITEM = 30
MAX_ITENS = 40
FOTO_MAX = 1_500_000
MIMES_FOTO = {b'\xff\xd8\xff': 'image/jpeg', b'\x89PNG': 'image/png', b'RIFF': 'image/webp'}

# limite simples por IP (por processo do gunicorn): evita alguém encher a lista de pedidos
_tentativas = defaultdict(deque)
LIMITE_PEDIDOS, JANELA = 6, 600


def _ip():
    return request.headers.get('CF-Connecting-IP') or request.headers.get('X-Forwarded-For', '').split(',')[0].strip() \
        or request.remote_addr or '?'


def _excedeu_limite():
    fila, agora_s = _tentativas[_ip()], time.monotonic()
    while fila and agora_s - fila[0] > JANELA:
        fila.popleft()
    if len(fila) >= LIMITE_PEDIDOS:
        return True
    fila.append(agora_s)
    return False


def estoque_livre():
    """Estoque de cada produto descontando o que já está reservado para pedidos em aberto."""
    pedidos, situacao = alocar()
    reservado = defaultdict(int)
    for ped in pedidos:
        for it in ped.itens:
            reservado[it.produto_id] += situacao[it.id][0]
    return lambda prod: max((prod.quantidade or 0) - reservado.get(prod.id, 0), 0)


def _vitrine():
    livre = estoque_livre()
    produtos = Produto.query.filter_by(na_loja=True).order_by(Produto.categoria, Produto.nome).all()
    itens = []
    for p in produtos:
        disp = livre(p)
        if disp > 0 and p.preco > 0:
            itens.append({'id': p.id, 'nome': p.nome, 'preco': round(p.preco, 2), 'max': min(disp, MAX_POR_ITEM),
                          'categoria': (p.categoria or 'Outros').strip() or 'Outros', 'descricao': p.descricao or '',
                          'foto': url_for('loja.foto', id=p.id, v=p.foto.versao) if p.foto else None})
    return itens


def _whatsapp_loja(emp):
    d = re.sub(r'\D', '', emp.loja_whatsapp or emp.telefone or '')
    if len(d) in (10, 11):
        d = '55' + d
    return d if len(d) in (12, 13) else None


def _pix_ok(emp):
    return bool(emp.pix_chave and emp.pix_nome and emp.pix_cidade)


@bp.after_request
def _cabecalhos(resp):
    resp.headers.setdefault('X-Content-Type-Options', 'nosniff')
    resp.headers.setdefault('Referrer-Policy', 'same-origin')
    resp.headers.setdefault('X-Frame-Options', 'DENY')
    return resp


# ---------------------------------------------------------------- público

@bp.route('/')
def index():
    emp = Empresa.atual()
    if not emp.loja_aberta:
        return render_template('loja/fechada.html', empresa=emp), 503
    itens = _vitrine()
    categorias = list(dict.fromkeys(i['categoria'] for i in itens))
    pagamentos = [p for p in PAGAMENTOS if p != 'Pix' or _pix_ok(emp)]
    return render_template('loja/index.html', empresa=emp, itens=itens, categorias=categorias, pagamentos=pagamentos)


@bp.route('/foto/<int:id>')
def foto(id):
    f = db.session.get(ProdutoFoto, id)
    if f is None:
        abort(404)
    return Response(f.dados, mimetype=f.mime, headers={'Cache-Control': 'public, max-age=31536000, immutable'})


@bp.route('/pedido', methods=['POST'])
def fazer_pedido():
    emp = Empresa.atual()
    if not emp.loja_aberta:
        return jsonify(erro='A loja está fechada no momento.'), 503
    dados = request.get_json(silent=True) or {}
    if dados.get('site'):                       # campo isca: só robô preenche
        return jsonify(erro='Pedido recusado.'), 400
    if _excedeu_limite():
        return jsonify(erro='Muitos pedidos seguidos deste aparelho. Espere alguns minutos ou chame no WhatsApp.'), 429

    nome = re.sub(r'\s+', ' ', str(dados.get('nome') or '')).strip()[:150]
    whats = re.sub(r'\D', '', str(dados.get('whatsapp') or ''))
    if whats.startswith('55') and len(whats) in (12, 13):
        whats = whats[2:]
    entrega = re.sub(r'\s+', ' ', str(dados.get('entrega') or '')).strip()[:120]
    pagamento = str(dados.get('pagamento') or '')
    obs = re.sub(r'\s+', ' ', str(dados.get('observacao') or '')).strip()[:255]
    if len(nome) < 2:
        return jsonify(erro='Informe seu nome.'), 400
    if len(whats) not in (10, 11):
        return jsonify(erro='Informe o WhatsApp com DDD.'), 400
    if not entrega:
        return jsonify(erro='Informe o bloco e o apartamento.'), 400
    if pagamento not in PAGAMENTOS or (pagamento == 'Pix' and not _pix_ok(emp)):
        return jsonify(erro='Escolha a forma de pagamento.'), 400

    pedidos_itens = {}
    for it in (dados.get('itens') or [])[:MAX_ITENS]:
        try:
            pid, q = int(it.get('id')), int(it.get('qtd'))
        except (TypeError, ValueError, AttributeError):
            return jsonify(erro='Carrinho inválido. Recarregue a página.'), 400
        if q > 0:
            pedidos_itens[pid] = pedidos_itens.get(pid, 0) + q
    if not pedidos_itens:
        return jsonify(erro='Seu carrinho está vazio.'), 400

    # trava as linhas dos produtos: dois pedidos ao mesmo tempo não vendem a mesma unidade
    produtos = {p.id: p for p in Produto.query.filter(Produto.id.in_(pedidos_itens)).with_for_update().all()}
    livre = estoque_livre()
    faltou = []
    for pid, q in pedidos_itens.items():
        p = produtos.get(pid)
        if p is None or not p.na_loja or p.preco <= 0:
            faltou.append({'id': pid, 'nome': 'Produto indisponível', 'disponivel': 0})
        elif q > min(livre(p), MAX_POR_ITEM):
            faltou.append({'id': pid, 'nome': p.nome, 'disponivel': min(livre(p), MAX_POR_ITEM)})
    if faltou:
        db.session.rollback()
        nomes = ', '.join(f"{f['nome']} (tem {f['disponivel']})" for f in faltou)
        return jsonify(erro=f'Alguns itens acabaram de ser vendidos: {nomes}. Ajustei seu carrinho.', faltou=faltou), 409

    cliente = Cliente.query.filter_by(whatsapp=whats).order_by(Cliente.id).first()
    if cliente is None:
        cliente = Cliente(nome=nome, whatsapp=whats, criado_em=datetime.now())
        db.session.add(cliente)
        db.session.flush()

    pedido = Pedido(cliente_id=cliente.id, criado_em=agora(), origem='loja', codigo=secrets.token_urlsafe(9),
                    entrega=entrega, pagamento=pagamento,
                    # cliente já cadastrado com outro nome (ex.: alguém da mesma casa): guarda o nome digitado
                    observacao=' · '.join(filter(None, [f'Nome no pedido: {nome}' if cliente.nome != nome else '',
                                                        obs]))[:255] or None)
    for pid, q in pedidos_itens.items():
        pedido.itens.append(PedidoItem(produto_id=pid, quantidade=q, preco_unitario=round(produtos[pid].preco, 2)))
    db.session.add(pedido)
    db.session.commit()
    return jsonify(ok=True, url=url_for('loja.ver_pedido', codigo=pedido.codigo, novo=1))


@bp.route('/p/<codigo>')
def ver_pedido(codigo):
    if not re.fullmatch(r'[A-Za-z0-9_-]{8,16}', codigo):
        abort(404)
    pedido = Pedido.query.filter_by(codigo=codigo, origem='loja').first_or_404()
    emp = Empresa.atual()
    pix_txt = qr = None
    if pedido.pagamento == 'Pix' and pedido.status == 'aberto' and _pix_ok(emp):
        pix_txt = pix.payload(emp.pix_chave, emp.pix_nome, emp.pix_cidade, pedido.total, txid=f'PED{pedido.id}')
        qr = pix.qr_svg(pix_txt)
    zap = _whatsapp_loja(emp)
    link_zap = None
    if zap:
        linhas = [f'Olá! Fiz o pedido #{pedido.id} na loja:']
        linhas += [f'• {it.quantidade}x {it.produto.nome}' for it in pedido.itens]
        linhas += [f'Total: R$ {pedido.total:.2f}'.replace('.', ','), f'Entrega: {pedido.entrega}',
                   f'Pagamento: {pedido.pagamento}', '', 'https://' + request.host + url_for('loja.ver_pedido', codigo=codigo)]
        link_zap = f'https://wa.me/{zap}?text={quote(chr(10).join(linhas))}'
    return render_template('loja/pedido.html', pedido=pedido, empresa=emp, pix_txt=pix_txt, qr=qr,
                           link_zap=link_zap, STATUS=STATUS_CLIENTE, novo=request.args.get('novo') == '1')


# ---------------------------------------------------------------- administração (com login)

@bp_admin.route('/', methods=['GET', 'POST'])
def config():
    emp = Empresa.atual()
    if request.method == 'POST':
        emp.loja_aberta = request.form.get('loja_aberta') == '1'
        emp.loja_aviso = (request.form.get('loja_aviso') or '').strip()[:300] or None
        zap = re.sub(r'\D', '', request.form.get('loja_whatsapp') or '')
        if zap.startswith('55') and len(zap) in (12, 13):
            zap = zap[2:]
        if zap and len(zap) not in (10, 11):
            flash('WhatsApp da loja: informe DDD + número.', 'danger')
            return redirect(url_for('loja_admin.config'))
        emp.loja_whatsapp = zap or None
        chave = (request.form.get('pix_chave') or '').strip()
        emp.pix_chave = pix.normalizar_chave(chave)[:77] if chave else None
        emp.pix_nome = (request.form.get('pix_nome') or '').strip()[:25] or None
        emp.pix_cidade = (request.form.get('pix_cidade') or '').strip()[:15] or None
        db.session.commit()
        flash('Loja ' + ('ABERTA: os clientes já podem pedir.' if emp.loja_aberta else 'fechada (ninguém consegue pedir).'),
              'success' if emp.loja_aberta else 'info')
        return redirect(url_for('loja_admin.config'))

    livre = estoque_livre()
    filtro = request.args.get('ver', 'estoque')
    todas = [{'p': p, 'livre': livre(p)} for p in Produto.query.order_by(Produto.categoria, Produto.nome).all()]
    na_vitrine = sum(1 for l in todas if l['p'].na_loja and l['livre'] > 0 and l['p'].preco > 0)
    if filtro == 'estoque':
        linhas = [l for l in todas if l['p'].quantidade > 0]
    elif filtro == 'sem-foto':
        linhas = [l for l in todas if l['p'].quantidade > 0 and l['p'].foto is None]
    else:
        filtro, linhas = 'todos', todas
    exemplo_pix = None
    if _pix_ok(emp):
        exemplo_pix = pix.payload(emp.pix_chave, emp.pix_nome, emp.pix_cidade, 1.00, txid='TESTE')
    return render_template('loja_admin.html', empresa=emp, linhas=linhas, filtro=filtro, na_vitrine=na_vitrine,
                           exemplo_pix=exemplo_pix, qr_exemplo=pix.qr_svg(exemplo_pix) if exemplo_pix else None)


@bp_admin.route('/produto/<int:id>', methods=['POST'])
def salvar_produto(id):
    p = db.get_or_404(Produto, id)
    acao = request.form.get('acao')
    if acao == 'foto':
        arq = request.files.get('foto')
        dados = arq.read(FOTO_MAX + 1) if arq else b''
        mime = next((m for assinatura, m in MIMES_FOTO.items() if dados.startswith(assinatura)), None)
        if not dados or mime is None:
            return jsonify(erro='Envie uma imagem JPG, PNG ou WebP.'), 400
        if len(dados) > FOTO_MAX:
            return jsonify(erro='Imagem grande demais (máx. 1,5 MB).'), 400
        if p.foto is None:
            p.foto = ProdutoFoto(dados=dados, mime=mime, atualizado_em=datetime.now())
        else:
            p.foto.dados, p.foto.mime, p.foto.atualizado_em = dados, mime, datetime.now()
        db.session.commit()
        return jsonify(ok=True, url=url_for('loja.foto', id=p.id, v=p.foto.versao))
    if acao == 'tirar_foto':
        p.foto = None
        db.session.commit()
        return jsonify(ok=True)
    if acao == 'dados':
        p.na_loja = request.form.get('na_loja') == '1'
        p.descricao = (request.form.get('descricao') or '').strip()[:300] or None
        db.session.commit()
        return jsonify(ok=True)
    abort(400)


def pedidos_loja_novos():
    """Para o selo no menu: pedidos da loja em aberto."""
    return Pedido.query.filter_by(origem='loja', status='aberto').count()
