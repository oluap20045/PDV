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
from datetime import datetime, timedelta
from urllib.parse import quote

from flask import Blueprint, Response, abort, flash, jsonify, redirect, render_template, request, url_for

from app import db
from app.models import Cliente, Empresa, LojaEvento, Pedido, PedidoItem, Produto, ProdutoFoto, TIPOS_EVENTO
from app.pedidos import agora, alocar
from app import pix
from app.combos import agrupar, aplicar as aplicar_combos, combo_dict, combos_validos

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


DIAS_SEMANA = ['seg', 'ter', 'qua', 'qui', 'sex', 'sáb', 'dom']
DIAS_NOMES = ['segunda', 'terça', 'quarta', 'quinta', 'sexta', 'sábado', 'domingo']


def _quando(momento):
    """'hoje às 18:00', 'amanhã às 18:00', 'sáb. às 18:00'"""
    if momento is None:
        return None
    dias = (momento.date() - agora().date()).days
    dia = 'hoje' if dias == 0 else 'amanhã' if dias == 1 else DIAS_SEMANA[momento.weekday()] + '.'
    return f'{dia} às {momento.strftime("%H:%M")}'


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
    aberta, proxima = emp.loja_situacao()
    if not aberta:
        return render_template('loja/fechada.html', empresa=emp, proxima=_quando(proxima)), 503
    itens = _vitrine()
    categorias = list(dict.fromkeys(i['categoria'] for i in itens))
    pagamentos = [p for p in PAGAMENTOS if p != 'Pix' or _pix_ok(emp)]
    na_vitrine = {i['id'] for i in itens}
    por_id = {i['id']: i for i in itens}
    # só mostra o combo se o estoque livre (já descontadas as reservas) der para fechar pelo menos 1
    combos = [d for d in (combo_dict(c, na_vitrine) for c in combos_validos('loja'))
              if sum(por_id[pid]['max'] for pid in d['produtos']) >= d['quantidade']]
    for c in combos:
        opcoes = sorted((por_id[pid] for pid in c['produtos']), key=lambda i: -i['preco'])
        c['fotos'] = [i['foto'] for i in opcoes if i['foto']][:3]
        c['cada'] = round(c['preco'] / c['quantidade'], 2)
        # "economize até": levando as opções mais caras (o cálculo real vem no carrinho)
        c['economia_max'] = round(opcoes[0]['preco'] * c['quantidade'] - c['preco'], 2) if opcoes else 0
    for i in itens:
        i['combos'] = [c['id'] for c in combos if i['id'] in c['produtos']]
    return render_template('loja/index.html', empresa=emp, itens=itens, categorias=categorias, pagamentos=pagamentos,
                           combos=combos)


@bp.route('/foto/<int:id>')
def foto(id):
    f = db.session.get(ProdutoFoto, id)
    if f is None:
        abort(404)
    return Response(f.dados, mimetype=f.mime, headers={'Cache-Control': 'public, max-age=31536000, immutable'})


@bp.route('/pedido', methods=['POST'])
def fazer_pedido():
    emp = Empresa.atual()
    aberta, proxima = emp.loja_situacao()
    if not aberta:
        msg = 'A loja acabou de fechar.' + (f' Abrimos {_quando(proxima)}.' if proxima else '')
        return jsonify(erro=msg), 503
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
    # combos ("4 por 12") entram sozinhos; cada unidade continua sendo do seu produto
    grupos, resto = aplicar_combos([(pid, q, round(produtos[pid].preco, 2)) for pid, q in pedidos_itens.items()],
                                   [combo_dict(c) for c in combos_validos('loja')])
    for n, g in enumerate(grupos, 1):
        for pid, q, preco in g['linhas']:
            pedido.itens.append(PedidoItem(produto_id=pid, quantidade=q, preco_unitario=preco,
                                           combo_id=g['combo']['id'], combo_grupo=n))
    for pid, q in resto.items():
        pedido.itens.append(PedidoItem(produto_id=pid, quantidade=q, preco_unitario=round(produtos[pid].preco, 2)))
    db.session.add(pedido)
    db.session.commit()
    return jsonify(ok=True, url=url_for('loja.ver_pedido', codigo=pedido.codigo, novo=1))


# ---------------------------------------------------------------- analisador de tráfego (público, só grava)

_eventos_ip = defaultdict(deque)
LIMITE_EVENTOS = 300                     # por IP a cada 10 min: sobra para uma pessoa, segura um robô
ROBOS = re.compile(r'bot|crawl|spider|slurp|preview|facebookexternalhit|whatsapp|headless|lighthouse|curl|wget|python',
                   re.I)


def _dispositivo(ua):
    if re.search(r'iPad|Tablet', ua):
        return 'tablet'
    return 'celular' if re.search(r'Mobi|Android|iPhone', ua) else 'computador'


@bp.route('/evento', methods=['POST'])
def evento():
    """Recebe acessos e cliques do rastreio.js. Sempre responde 204: estatística nunca quebra a página."""
    ua = request.user_agent.string or ''
    if not ua or ROBOS.search(ua):
        return '', 204
    fila, agora_s = _eventos_ip[_ip()], time.monotonic()
    while fila and agora_s - fila[0] > JANELA:
        fila.popleft()
    if len(fila) >= LIMITE_EVENTOS:
        return '', 204
    dados = request.get_json(force=True, silent=True)
    if not isinstance(dados, dict):
        return '', 204
    visitante = re.sub(r'[^a-f0-9]', '', str(dados.get('v') or ''))[:24]
    if len(visitante) != 24:
        return '', 204
    origem = re.sub(r'[^a-z0-9._-]', '', str(dados.get('o') or '').lower())[:40] or 'direto'
    pagina = str(dados.get('p') or '')
    pagina = pagina if pagina in ('loja', 'pedido', 'fechada') else None
    disp, momento = _dispositivo(ua), agora()
    eventos = dados.get('eventos') if isinstance(dados.get('eventos'), list) else []
    for ev in eventos[:10]:
        if not isinstance(ev, dict) or ev.get('t') not in TIPOS_EVENTO:
            continue
        try:
            pid = int(ev['id']) if ev.get('id') is not None else None
        except (TypeError, ValueError):
            pid = None
        alvo = re.sub(r'\s+', ' ', str(ev.get('a') or '')).strip()[:120] or None
        fila.append(agora_s)
        db.session.add(LojaEvento(criado_em=momento, visitante=visitante, tipo=ev['t'], alvo=alvo, produto_id=pid,
                                  pagina=pagina, origem=origem, dispositivo=disp))
    db.session.commit()
    return '', 204


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
        for bloco in agrupar(pedido.itens):
            if bloco[0] == 'combo':
                linhas.append(f'• Combo {bloco[1].nome}: ' + ', '.join(f'{it.quantidade}x {it.produto.nome}' for it in bloco[2]))
            else:
                linhas.append(f'• {bloco[1].quantidade}x {bloco[1].produto.nome}')
        linhas += [f'Total: R$ {pedido.total:.2f}'.replace('.', ','), f'Entrega: {pedido.entrega}',
                   f'Pagamento: {pedido.pagamento}']
        horario = emp.horario_texto(pedido.criado_em)
        if horario:
            linhas.append(f'Entregas: das {horario}')
        linhas += ['', 'https://' + request.host + url_for('loja.ver_pedido', codigo=codigo)]
        link_zap = f'https://wa.me/{zap}?text={quote(chr(10).join(linhas))}'
    return render_template('loja/pedido.html', pedido=pedido, empresa=emp, pix_txt=pix_txt, qr=qr, blocos=agrupar(pedido.itens),
                           link_zap=link_zap, STATUS=STATUS_CLIENTE, novo=request.args.get('novo') == '1')


# ---------------------------------------------------------------- administração (com login)

@bp_admin.route('/', methods=['GET', 'POST'])
def config():
    emp = Empresa.atual()
    if request.method == 'POST':
        modo = request.form.get('loja_modo')
        if modo in ('auto', 'aberta', 'fechada'):
            emp.loja_modo = modo
        grade = []
        for i, nome in enumerate(DIAS_NOMES):
            if request.form.get(f'dia{i}_aberto') != '1':
                grade.append(None)
                continue
            try:
                abre = datetime.strptime(request.form.get(f'dia{i}_abre') or '', '%H:%M').time()
                fecha = datetime.strptime(request.form.get(f'dia{i}_fecha') or '', '%H:%M').time()
            except ValueError:
                db.session.rollback()
                flash(f'Horário de {nome} inválido.', 'danger')
                return redirect(url_for('loja_admin.config'))
            if abre == fecha:
                db.session.rollback()
                flash(f'{nome.capitalize()}: o horário de abrir e de fechar não podem ser iguais.', 'danger')
                return redirect(url_for('loja_admin.config'))
            grade.append((abre, fecha))
        if emp.loja_modo == 'auto' and not any(grade):
            db.session.rollback()
            flash('No automático, deixe pelo menos um dia aberto.', 'danger')
            return redirect(url_for('loja_admin.config'))
        emp.loja_grade = grade
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
        aberta, proxima = emp.loja_situacao()
        msg = {'auto': 'Automático: ' + ('aberta agora.' if aberta else f'fechada agora, abre {_quando(proxima)}.'),
               'aberta': 'Loja ABERTA até você fechar.', 'fechada': 'Loja FECHADA até você abrir.'}[emp.loja_modo]
        flash('Salvo. ' + msg, 'success' if aberta else 'info')
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
    aberta, proxima = emp.loja_situacao()
    return render_template('loja_admin.html', empresa=emp, linhas=linhas, aberta=aberta, proxima=_quando(proxima),
                           DIAS=DIAS_SEMANA, DIAS_NOMES=DIAS_NOMES, filtro=filtro, na_vitrine=na_vitrine,
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


# ---------------------------------------------------------------- relatório de acessos (com login)

PERIODOS = {'hoje': ('Hoje', 1), '7': ('7 dias', 7), '30': ('30 dias', 30), '90': ('90 dias', 90)}
GUARDAR_DIAS = 400


def _contagem(pares):
    """[(chave, visitante)] -> [(chave, visitantes distintos, cliques)] do maior para o menor."""
    vis, cliques = defaultdict(set), defaultdict(int)
    for chave, v in pares:
        vis[chave].add(v)
        cliques[chave] += 1
    return sorted(((k, len(vis[k]), cliques[k]) for k in vis), key=lambda x: (-x[1], -x[2], str(x[0])))


@bp_admin.route('/acessos')
def acessos():
    periodo = request.args.get('periodo', '7')
    if periodo not in PERIODOS:
        periodo = '7'
    _, dias = PERIODOS[periodo]
    agora_ = agora()
    hoje = agora_.replace(hour=0, minute=0, second=0, microsecond=0)
    inicio = hoje - timedelta(days=dias - 1)

    # limpeza: estatística antiga não serve para nada e só ocupa o banco
    LojaEvento.query.filter(LojaEvento.criado_em < hoje - timedelta(days=GUARDAR_DIAS)).delete(synchronize_session=False)
    db.session.commit()

    eventos = (LojaEvento.query.filter(LojaEvento.criado_em >= inicio)
               .order_by(LojaEvento.criado_em).limit(300_000).all())
    visitas = [e for e in eventos if e.tipo == 'visita']
    quem = lambda tipo: {e.visitante for e in eventos if e.tipo == tipo}
    visitantes = {e.visitante for e in visitas}
    ja_vieram = {v for (v,) in db.session.query(LojaEvento.visitante).filter(
        LojaEvento.criado_em < inicio, LojaEvento.visitante.in_(visitantes)).distinct()} if visitantes else set()

    funil = [('Entraram na loja', len({e.visitante for e in visitas if e.pagina in ('loja', None)})),
             ('Adicionaram algo ao carrinho', len(quem('adicionar'))),
             ('Abriram o carrinho', len(quem('carrinho'))),
             ('Fizeram pedido', len(quem('pedido')))]

    # visitantes por dia (ou por hora, se o período é só hoje)
    serie = []
    if dias == 1:
        for h in range(agora_.hour + 1):
            serie.append((f'{h:02d}h', len({e.visitante for e in visitas if e.criado_em.hour == h})))
    else:
        por_dia = defaultdict(set)
        for e in visitas:
            por_dia[e.criado_em.date()].add(e.visitante)
        for i in range(dias):
            d = (inicio + timedelta(days=i)).date()
            serie.append((f'{DIAS_SEMANA[d.weekday()]} {d:%d/%m}', len(por_dia.get(d, ()))))   # eixo mostra só dd/mm
    pico = []
    if dias > 1:
        por_hora = defaultdict(set)
        for e in visitas:
            por_hora[e.criado_em.hour].add(e.visitante)
        pico = [(f'{h:02d}h', len(por_hora.get(h, ()))) for h in range(24)]

    # primeira origem e aparelho de cada visitante no período
    origem_de, aparelho_de = {}, {}
    for e in visitas:
        origem_de.setdefault(e.visitante, e.origem or 'direto')
        aparelho_de.setdefault(e.visitante, e.dispositivo or '?')

    pedidos_reais = Pedido.query.filter(Pedido.origem == 'loja', Pedido.criado_em >= inicio,
                                        Pedido.status != 'cancelado').all()
    cards = {
        'visitantes': len(visitantes),
        'novos': len(visitantes - ja_vieram),
        'voltaram': len(visitantes & ja_vieram),
        'paginas': len(visitas),
        'fechada': len({e.visitante for e in visitas if e.pagina == 'fechada'}),
        'pedidos': len(pedidos_reais),
        'vendido': round(sum(p.total for p in pedidos_reais), 2),
        'conversao': round(100 * len(quem('pedido')) / len(visitantes), 1) if visitantes else 0,
    }
    return render_template(
        'loja_acessos.html', periodo=periodo, PERIODOS=PERIODOS, cards=cards, funil=funil, serie=serie, pico=pico,
        produtos=_contagem((e.alvo or f'Produto {e.produto_id}', e.visitante) for e in eventos if e.tipo == 'adicionar'),
        categorias=_contagem((e.alvo or 'Tudo', e.visitante) for e in eventos if e.tipo == 'categoria'),
        cliques=_contagem((TIPOS_EVENTO[e.tipo] + (f' — {e.alvo}' if e.tipo == 'clique' and e.alvo else ''), e.visitante)
                          for e in eventos if e.tipo not in ('visita', 'adicionar', 'categoria')),
        origens=_contagem((o, v) for v, o in origem_de.items()),
        aparelhos=_contagem((a, v) for v, a in aparelho_de.items()),
        recentes=list(reversed(eventos[-40:])), TIPOS=TIPOS_EVENTO)
