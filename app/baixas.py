"""Baixa de estoque sem venda: brinde, degustação, perda, vencido, consumo próprio.

Só tira do estoque. NÃO cria lançamento no financeiro: o custo da mercadoria já saiu do caixa quando ela
foi comprada. A baixa guarda o custo médio da hora para mostrar quanto (a custo) foi embora por motivo.
"""
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import current_user

from app import db
from app.models import BaixaEstoque, MOTIVOS_BAIXA, Produto, Cliente

bp = Blueprint('baixas', __name__)


def agora():
    return datetime.now(ZoneInfo('America/Sao_Paulo')).replace(tzinfo=None)


def _periodo():
    hoje = agora().date()
    inicio, fim = hoje.replace(day=1), hoje
    try:
        if request.args.get('inicio'):
            inicio = datetime.strptime(request.args['inicio'], '%Y-%m-%d').date()
        if request.args.get('fim'):
            fim = datetime.strptime(request.args['fim'], '%Y-%m-%d').date()
    except ValueError:
        flash('Data inválida; mostrando este mês.', 'warning')
        inicio, fim = hoje.replace(day=1), hoje
    if fim < inicio:
        inicio, fim = fim, inicio
    return inicio, fim


def _itens_do_form():
    """produto_id[] / quantidade[] -> [(produto, qtd)], juntando repetidos e conferindo o estoque."""
    qtd_por_produto = {}
    for pid, q in zip(request.form.getlist('produto_id'), request.form.getlist('quantidade')):
        if not pid:
            continue
        try:
            q = int(q)
        except (TypeError, ValueError):
            q = 0
        prod = db.session.get(Produto, int(pid))
        if prod is None:
            raise ValueError('Produto não encontrado.')
        if q <= 0:
            raise ValueError(f'Quantidade inválida em {prod.nome}.')
        qtd_por_produto[prod] = qtd_por_produto.get(prod, 0) + q
    if not qtd_por_produto:
        raise ValueError('Inclua pelo menos um produto.')
    for prod, q in qtd_por_produto.items():
        if q > max(prod.quantidade or 0, 0):
            raise ValueError(f'{prod.nome}: só tem {max(prod.quantidade or 0, 0)} no estoque (pediu baixa de {q}).')
    return list(qtd_por_produto.items())


@bp.route('/estoque/baixas', methods=['GET', 'POST'])
def baixas():
    if request.method == 'POST':
        motivo = request.form.get('motivo')
        try:
            if motivo not in MOTIVOS_BAIXA:
                raise ValueError('Escolha o motivo da baixa.')
            itens = _itens_do_form()
        except ValueError as e:
            flash(str(e), 'danger')
            return redirect(url_for('baixas.baixas', produto=request.form.get('produto_id')))
        cliente_id = request.form.get('cliente_id', type=int) or None
        if cliente_id and db.session.get(Cliente, cliente_id) is None:
            cliente_id = None
        obs = (request.form.get('observacao') or '').strip()[:255] or None
        quando = agora()
        total_un, total_custo = 0, 0.0
        for prod, q in itens:
            prod.quantidade = (prod.quantidade or 0) - q
            b = BaixaEstoque(data=quando, produto_id=prod.id, quantidade=q, custo_unitario=round(prod.custo or 0, 4),
                             motivo=motivo, observacao=obs, cliente_id=cliente_id, usuario_id=current_user.id)
            db.session.add(b)
            total_un += q
            total_custo += b.valor_custo
        db.session.commit()
        flash(f'Baixa de {total_un} unidade(s) como {MOTIVOS_BAIXA[motivo].lower()} '
              f'(R$ {total_custo:.2f} a custo). Saiu do estoque; nada foi lançado no financeiro.', 'success')
        return redirect(url_for('baixas.baixas'))

    inicio, fim = _periodo()
    q = (BaixaEstoque.query
         .filter(BaixaEstoque.data >= datetime.combine(inicio, datetime.min.time()),
                 BaixaEstoque.data < datetime.combine(fim + timedelta(days=1), datetime.min.time()))
         .order_by(BaixaEstoque.data.desc(), BaixaEstoque.id.desc()))
    motivo_filtro = request.args.get('motivo')
    if motivo_filtro in MOTIVOS_BAIXA:
        q = q.filter(BaixaEstoque.motivo == motivo_filtro)
    lista = q.all()

    totais = {}
    for b in lista:
        if b.estornada_em:
            continue
        t = totais.setdefault(b.motivo, {'motivo': b.motivo_nome, 'chave': b.motivo, 'unidades': 0, 'valor': 0.0})
        t['unidades'] += b.quantidade
        t['valor'] = round(t['valor'] + b.valor_custo, 2)
    resumo = sorted(totais.values(), key=lambda t: -t['valor'])
    total = {'unidades': sum(t['unidades'] for t in resumo), 'valor': round(sum(t['valor'] for t in resumo), 2)}

    produtos = Produto.query.filter(Produto.quantidade > 0).order_by(Produto.nome).all()
    codigos = {}
    for p in produtos:
        for c in (p.codigo_barras, p.codigo_fornecedor):
            if c and c.strip():
                codigos.setdefault(c.strip(), p.id)
    produtos_js = {p.id: {'nome': p.nome, 'estoque': p.quantidade, 'custo': round(p.custo or 0, 2),
                          'codigo': p.codigo_fornecedor or p.codigo_barras or ''} for p in produtos}
    clientes = Cliente.query.filter_by(padrao=False).order_by(Cliente.nome).all()
    hoje = agora().date()
    atalhos = [('Este mês', hoje.replace(day=1), hoje),
               ('Mês passado', (hoje.replace(day=1) - timedelta(days=1)).replace(day=1), hoje.replace(day=1) - timedelta(days=1)),
               ('Este ano', date(hoje.year, 1, 1), hoje)]
    return render_template('baixas.html', lista=lista, resumo=resumo, total=total, inicio=inicio, fim=fim,
                           motivo_filtro=motivo_filtro, motivos=MOTIVOS_BAIXA, produtos=produtos,
                           produtos_js=produtos_js, codigos=codigos, clientes=clientes, atalhos=atalhos,
                           produto_inicial=request.args.get('produto', type=int))


@bp.route('/estoque/baixa/<int:id>/estornar', methods=['POST'])
def estornar(id):
    """Desfaz uma baixa lançada errado: a quantidade volta para o estoque."""
    b = db.get_or_404(BaixaEstoque, id)
    if b.estornada_em is None:
        from app.precificacao import registrar_entrada
        registrar_entrada(b.produto, b.quantidade, b.custo_unitario or b.produto.custo or 0)
        b.estornada_em = agora()
        db.session.commit()
        flash(f'Baixa estornada: {b.quantidade} × {b.produto.nome} voltaram para o estoque.', 'info')
    return redirect(url_for('baixas.baixas'))
