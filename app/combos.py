"""Combos / promoções: "leve N por R$ X", o cliente escolhe entre os produtos do combo.

Regra (igual no Python e no static/js/combos.js — mexeu num, mexa no outro):
- só entram unidades vendidas a preço de tabela (preço mexido à mão no PDV = fica fora do combo);
- combos com menor preço por unidade são montados primeiro; empate = o mais antigo (menor id);
- dentro do combo entram primeiro as unidades mais caras (o cliente sempre sai ganhando);
- só monta o combo se ele sair mais barato que a soma dos preços de tabela;
- o preço do combo é dividido igualmente entre as unidades; os centavos que sobram vão para as últimas.
Cada unidade continua sendo do seu produto: baixa o estoque certo e guarda o custo certo.
"""
from datetime import datetime

from flask import Blueprint, flash, redirect, render_template, request, url_for

from app import db
from app.models import Combo, ItemVenda, PedidoItem, Produto
from app.pedidos import agora

bp = Blueprint('combos', __name__, url_prefix='/combos')


# ---------------------------------------------------------------- regra

def combos_validos(onde):
    """Combos que valem hoje no 'pdv' ou na 'loja'."""
    hoje = agora().date()
    q = Combo.query.filter_by(ativo=True)
    q = q.filter_by(no_pdv=True) if onde == 'pdv' else q.filter_by(na_loja=True)
    return [c for c in q.order_by(Combo.id).all() if c.valido(hoje)]


def combo_dict(c, so_produtos=None):
    ids = [p.id for p in c.produtos if so_produtos is None or p.id in so_produtos]
    return {'id': c.id, 'nome': c.nome, 'quantidade': c.quantidade, 'preco': round(c.preco, 2), 'produtos': ids,
            'titulo': c.titulo}


def _distribuir(pegar, preco, n):
    """[(pid, qtd)] -> [(pid, qtd, preço unitário)] somando exatamente `preco`."""
    centavos = round(preco * 100)
    base, sobra = divmod(centavos, n)
    linhas, i = [], 0
    for pid, k in pegar:
        for _ in range(k):
            unit = (base + (1 if i >= n - sobra else 0)) / 100
            if linhas and linhas[-1][0] == pid and linhas[-1][2] == unit:
                linhas[-1][1] += 1
            else:
                linhas.append([pid, 1, unit])
            i += 1
    return [tuple(l) for l in linhas]


def aplicar(itens, combos):
    """itens: [(produto_id, qtd, preço de tabela)] — só unidades que podem entrar em combo.
    combos: [combo_dict]. Devolve (grupos, resto):
      grupos = [{'combo': dict, 'linhas': [(pid, qtd, preço)], 'tabela': soma a preço cheio, 'economia': x}]
      resto  = {pid: qtd que ficou fora de combo}"""
    resto, preco = {}, {}
    for pid, q, p in itens:
        if q > 0:
            resto[pid] = resto.get(pid, 0) + q
            preco[pid] = p
    grupos = []
    for c in sorted(combos, key=lambda c: (round(c['preco'] * 100) / c['quantidade'], c['id'])):
        n = c['quantidade']
        if n < 1:
            continue
        eleg = sorted((pid for pid in set(c['produtos']) if resto.get(pid)), key=lambda pid: (-preco[pid], pid))
        while sum(resto[pid] for pid in eleg) >= n:
            pegar, falta = [], n
            for pid in eleg:
                k = min(resto[pid], falta)
                if k:
                    pegar.append((pid, k))
                    falta -= k
                if not falta:
                    break
            tabela = round(sum(preco[pid] * k for pid, k in pegar), 2)
            if tabela <= c['preco'] + 0.004:
                break
            for pid, k in pegar:
                resto[pid] -= k
            eleg = [pid for pid in eleg if resto[pid]]
            grupos.append({'combo': c, 'linhas': _distribuir(pegar, c['preco'], n), 'tabela': tabela,
                           'economia': round(tabela - c['preco'], 2)})
    return grupos, {pid: q for pid, q in resto.items() if q}


def conferir_grupos(linhas, onde):
    """Confere os combos que vieram prontos do PDV. linhas: [(produto, qtd, preço, combo_id, grupo)].
    Levanta ValueError com a explicação se algum combo não fecha."""
    validos = {c.id: c for c in combos_validos(onde)}
    grupos = {}
    for prod, q, preco, combo_id, grupo in linhas:
        if combo_id is None:
            continue
        grupos.setdefault(grupo, {'combo_id': combo_id, 'linhas': []})
        if grupos[grupo]['combo_id'] != combo_id:
            raise ValueError('combo misturado no carrinho; recarregue a página')
        grupos[grupo]['linhas'].append((prod, q, preco))
    for g in grupos.values():
        c = validos.get(g['combo_id'])
        if c is None:
            raise ValueError('um combo do carrinho não vale mais (desativado ou fora da validade); recarregue a página')
        ids = {p.id for p in c.produtos}
        if any(prod.id not in ids for prod, _, _ in g['linhas']):
            raise ValueError(f'produto fora do combo {c.nome}')
        if sum(q for _, q, _ in g['linhas']) != c.quantidade:
            raise ValueError(f'o combo {c.nome} precisa de {c.quantidade} unidades')
        if abs(sum(q * p for _, q, p in g['linhas']) - c.preco) > 0.011:
            raise ValueError(f'o preço do combo {c.nome} não confere')


def agrupar(itens):
    """Itens de venda/pedido -> blocos para mostrar: ('combo', combo, [itens], total) ou ('item', item)."""
    blocos, por_grupo = [], {}
    for it in itens:
        if it.combo_id and it.combo_grupo:
            chave = (it.combo_id, it.combo_grupo)
            if chave not in por_grupo:
                por_grupo[chave] = ['combo', it.combo, [], 0.0]
                blocos.append(por_grupo[chave])
            por_grupo[chave][2].append(it)
            por_grupo[chave][3] = round(por_grupo[chave][3] + it.quantidade * it.preco_unitario, 2)
        else:
            blocos.append(['item', it])
    return [tuple(b) for b in blocos]


# ---------------------------------------------------------------- cadastro (com login)

def _dados_do_form(combo):
    nome = ' '.join((request.form.get('nome') or '').split())[:80]
    try:
        n = int(request.form.get('quantidade') or 0)
        texto = (request.form.get('preco') or '0').replace('R$', '').strip()
        if ',' in texto:                                   # "1.234,50" -> 1234.50
            texto = texto.replace('.', '').replace(',', '.')
        preco = round(float(texto), 2)
    except ValueError:
        raise ValueError('Quantidade ou preço inválido.')
    datas = []
    for campo in ('inicio', 'fim'):
        v = request.form.get(campo) or ''
        try:
            datas.append(datetime.strptime(v, '%Y-%m-%d').date() if v else None)
        except ValueError:
            raise ValueError('Data inválida.')
    ids = {int(i) for i in request.form.getlist('produtos') if i.isdigit()}
    produtos = Produto.query.filter(Produto.id.in_(ids)).all() if ids else []
    if not nome:
        raise ValueError('Dê um nome ao combo (ex.: Trufas laCreme 4 por 12).')
    if not 2 <= n <= 50:
        raise ValueError('O combo precisa de 2 a 50 unidades.')
    if preco <= 0:
        raise ValueError('Informe o preço do combo.')
    if not produtos:
        raise ValueError('Marque os produtos que o cliente pode escolher.')
    if datas[0] and datas[1] and datas[1] < datas[0]:
        raise ValueError('O fim da validade é antes do início.')
    combo.nome, combo.quantidade, combo.preco = nome, n, preco
    combo.inicio, combo.fim = datas
    combo.ativo = request.form.get('ativo') == '1'
    combo.no_pdv = request.form.get('no_pdv') == '1'
    combo.na_loja = request.form.get('na_loja') == '1'
    combo.produtos = produtos
    if not (combo.no_pdv or combo.na_loja):
        raise ValueError('Marque onde o combo vale: PDV, loja online ou os dois.')


@bp.route('/')
def lista():
    hoje = agora().date()
    combos = Combo.query.order_by(Combo.ativo.desc(), Combo.nome).all()
    usos = dict(db.session.query(ItemVenda.combo_id, db.func.count(db.distinct(ItemVenda.venda_id)))
                .filter(ItemVenda.combo_id.isnot(None)).group_by(ItemVenda.combo_id).all())
    return render_template('combos.html', combos=combos, hoje=hoje, usos=usos)


@bp.route('/novo', methods=['GET', 'POST'])
@bp.route('/<int:id>', methods=['GET', 'POST'])
def editar(id=None):
    combo = db.get_or_404(Combo, id) if id else Combo(ativo=True, no_pdv=True, na_loja=True)
    if request.method == 'POST':
        try:
            with db.session.no_autoflush:
                _dados_do_form(combo)
        except ValueError as e:
            db.session.rollback()
            flash(str(e), 'danger')
            return render_template('combo_form.html', combo=combo, produtos=_produtos(), form=request.form)
        if combo.id is None:
            db.session.add(combo)
        db.session.commit()
        flash(f'Combo "{combo.nome}" salvo: {combo.titulo}.', 'success')
        return redirect(url_for('combos.lista'))
    return render_template('combo_form.html', combo=combo, produtos=_produtos(), form=None)


def _produtos():
    return Produto.query.order_by(Produto.categoria, Produto.nome).all()


@bp.route('/<int:id>/ativo', methods=['POST'])
def alternar(id):
    combo = db.get_or_404(Combo, id)
    combo.ativo = not combo.ativo
    db.session.commit()
    flash(f'Combo "{combo.nome}" {"ativado" if combo.ativo else "desativado"}.', 'success' if combo.ativo else 'info')
    return redirect(url_for('combos.lista'))


@bp.route('/<int:id>/excluir', methods=['POST'])
def excluir(id):
    combo = db.get_or_404(Combo, id)
    usado = (ItemVenda.query.filter_by(combo_id=combo.id).first() or PedidoItem.query.filter_by(combo_id=combo.id).first())
    if usado:
        combo.ativo = False
        db.session.commit()
        flash(f'O combo "{combo.nome}" já foi usado em vendas/pedidos: em vez de excluir, ele foi desativado '
              '(o histórico continua mostrando o combo).', 'info')
    else:
        db.session.delete(combo)
        db.session.commit()
        flash(f'Combo "{combo.nome}" excluído.', 'success')
    return redirect(url_for('combos.lista'))
