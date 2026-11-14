"""Sorteios: formulário público de inscrição com período definido + sorteio entre os inscritos.

`bp_publico` (/loja/sorteio/...) é PÚBLICO como a loja (passa pelo túnel: o Caddy só repassa /loja e /static).
`bp` (/sorteios/...) exige login: criar, ver inscritos e sortear.

Cada inscrição vira (ou reaproveita) um Cliente: o mesmo nome no mesmo bloco/apartamento é a mesma pessoa,
em qualquer sorteio. Assim a lista de clientes cresce sem duplicar (leads para as próximas promoções).
"""
import os
import re
import secrets
import time
import unicodedata
from collections import defaultdict, deque
from datetime import datetime, timedelta

from flask import Blueprint, abort, flash, jsonify, redirect, render_template, request, session, url_for

from app import db
from flask_login import current_user

from app.models import BaixaEstoque, Cliente, Empresa, Produto, Sorteio, SorteioInscricao
from app.pedidos import agora

bp_publico = Blueprint('sorteio_publico', __name__, url_prefix='/loja/sorteio')
bp = Blueprint('sorteios', __name__, url_prefix='/sorteios')

SITUACAO = {'agendado': 'Agendado', 'aberto': 'Inscrições abertas', 'encerrado': 'Aguardando sorteio',
            'sorteado': 'Sorteado'}

# limite por IP (por processo do gunicorn): uma família inteira se inscreve, um robô não enche a lista
_tentativas = defaultdict(deque)
LIMITE, JANELA = 8, 600


# ---------------------------------------------------------------- regras de cadastro (sem duplicar)

def chave_nome(nome):
    """'  José  da Silva ' -> 'jose da silva' (sem acento, minúsculo, espaços simples)."""
    s = unicodedata.normalize('NFKD', nome or '')
    s = ''.join(c for c in s if not unicodedata.combining(c))
    return re.sub(r'\s+', ' ', s).strip().lower()


def limpar_nome(nome):
    return re.sub(r'\s+', ' ', str(nome or '')).strip()[:150]


def limpar_bloco(valor):
    """'Bloco 01' / 'bl. a' / '1' -> '1' / 'A'."""
    s = chave_nome(str(valor or '')).upper()
    s = re.sub(r'^(BLOCO|BLC|BL)\b\.?', '', s)
    s = re.sub(r'[^A-Z0-9]', '', s)
    return (s.lstrip('0') or ('0' if s else ''))[:6]


def limpar_apto(valor):
    """'Apto 034' / 'ap 101-b' / '34' -> '34' / '101B'."""
    s = chave_nome(str(valor or '')).upper()
    s = re.sub(r'^(APARTAMENTO|APTO|APT|AP)\b\.?', '', s)
    s = re.sub(r'[^A-Z0-9]', '', s)
    return (s.lstrip('0') or ('0' if s else ''))[:8]


def limpar_whatsapp(valor):
    d = re.sub(r'\D', '', str(valor or ''))
    if d.startswith('55') and len(d) in (12, 13):
        d = d[2:]
    return d


def achar_ou_criar_cliente(nome, whatsapp, bloco, apto, origem='sorteio'):
    """Mesmo nome (sem acento/maiúscula) no mesmo bloco + apartamento = mesmo cliente.
    Senão, quem já tem esse WhatsApp e o mesmo primeiro nome, mas ainda sem apartamento, ganha o endereço.
    Senão, cliente novo (origem 'sorteio' ou 'loja')."""
    chave = chave_nome(nome)
    for c in Cliente.query.filter_by(bloco=bloco, apartamento=apto).order_by(Cliente.id).all():
        if chave_nome(c.nome) == chave:
            if whatsapp and c.whatsapp != whatsapp:
                c.whatsapp = whatsapp            # o número mais recente é o que a pessoa usa
            return c
    primeiro = chave.split(' ')[0]
    for c in Cliente.query.filter_by(whatsapp=whatsapp).order_by(Cliente.id).all():
        # cadastrado no balcão como "Ana" e agora "Ana Souza": mesmo WhatsApp + mesmo primeiro nome
        if not c.apartamento and chave_nome(c.nome).split(' ')[0] == primeiro:
            c.bloco, c.apartamento = bloco, apto
            return c
    c = Cliente(nome=nome, whatsapp=whatsapp, bloco=bloco, apartamento=apto, origem=origem, criado_em=datetime.now())
    db.session.add(c)
    db.session.flush()
    return c


def nome_publico(cliente):
    """'Maria, bloco 1' (só o primeiro nome e o bloco: nada de telefone nem apartamento na página pública)."""
    primeiro = (cliente.nome or '').split(' ')[0].capitalize()
    return f'{primeiro}, bloco {cliente.bloco}' if cliente.bloco else primeiro


def quando(momento):
    """'hoje às 18:00', 'amanhã às 18:00', 'sáb., 15/11 às 18:00'"""
    dias = (momento.date() - agora().date()).days
    dia = 'hoje' if dias == 0 else 'amanhã' if dias == 1 else \
        ['seg.', 'ter.', 'qua.', 'qui.', 'sex.', 'sáb.', 'dom.'][momento.weekday()] + momento.strftime(', %d/%m')
    return f'{dia} às {momento.strftime("%H:%M")}'


def sorteio_em_destaque():
    """O sorteio que a loja divulga: o aberto que termina primeiro; senão nenhum."""
    momento = agora()
    return Sorteio.query.filter(Sorteio.inicio <= momento, Sorteio.fim > momento).order_by(Sorteio.fim).first()


def _excedeu_limite():
    from app.loja import _ip
    fila, agora_s = _tentativas[_ip()], time.monotonic()
    while fila and agora_s - fila[0] > JANELA:
        fila.popleft()
    if len(fila) >= LIMITE:
        return True
    fila.append(agora_s)
    return False


def link_publico(caminho):
    """Endereço que funciona no celular de quem recebe: o da internet (1º de LOJA_HOST); sem ele, o desta tela."""
    host = (os.environ.get('LOJA_HOST') or '').split(',')[0].strip().lower()
    return (f'https://{host}' if host else request.host_url.rstrip('/')) + caminho


def _foto(s):
    p = s.produto
    return url_for('loja.foto', id=p.id, v=p.foto.versao) if p is not None and p.foto else None


# ---------------------------------------------------------------- público

@bp_publico.after_request
def _cabecalhos(resp):
    resp.headers.setdefault('X-Content-Type-Options', 'nosniff')
    resp.headers.setdefault('Referrer-Policy', 'same-origin')
    resp.headers.setdefault('X-Frame-Options', 'DENY')
    resp.headers.setdefault('Cache-Control', 'no-store')
    return resp


@bp_publico.route('/')
def atual():
    """Link fixo para divulgar: leva ao sorteio aberto (ou ao último, para ver o resultado)."""
    s = sorteio_em_destaque() or Sorteio.query.filter(Sorteio.inicio <= agora()).order_by(Sorteio.fim.desc()).first()
    if s is None:
        return render_template('loja/sorteio.html', empresa=Empresa.atual(), s=None), 404
    return redirect(url_for('sorteio_publico.pagina', codigo=s.codigo))


@bp_publico.route('/<codigo>', methods=['GET', 'POST'])
def pagina(codigo):
    s = Sorteio.query.filter_by(codigo=codigo).first_or_404()
    emp = Empresa.atual()
    momento = agora()
    situacao = s.situacao(momento)
    erro, form = None, {}
    chave_sessao = f'sorteio-{s.codigo}'

    if request.method == 'POST':
        form = {k: request.form.get(k, '') for k in ('nome', 'whatsapp', 'bloco', 'apartamento')}
        nome = limpar_nome(form['nome'])
        whats = limpar_whatsapp(form['whatsapp'])
        bloco, apto = limpar_bloco(form['bloco']), limpar_apto(form['apartamento'])
        if request.form.get('site'):                 # campo isca: só robô preenche
            abort(400)
        if situacao != 'aberto':
            erro = 'As inscrições deste sorteio estão encerradas.' if situacao != 'agendado' else \
                f'As inscrições abrem {quando(s.inicio)}.'
        elif len(chave_nome(nome)) < 3 or ' ' not in chave_nome(nome):
            erro = 'Informe seu nome e sobrenome.'
        elif len(whats) not in (10, 11):
            erro = 'Informe o WhatsApp com DDD.'
        elif not bloco or not apto:
            erro = 'Informe o bloco e o apartamento.'
        elif _excedeu_limite():
            erro = 'Muitas inscrições seguidas deste aparelho. Espere alguns minutos.'
        if not erro:
            # o cadastro de cliente acontece sempre (é o lead), mas no sorteio vale UMA inscrição por apartamento:
            # apê com mais moradores não tem mais chance
            cliente = achar_ou_criar_cliente(nome, whats, bloco, apto)
            do_apto = (SorteioInscricao.query.join(Cliente)
                       .filter(SorteioInscricao.sorteio_id == s.id, Cliente.bloco == bloco, Cliente.apartamento == apto)
                       .first())
            if do_apto is None:
                db.session.add(SorteioInscricao(sorteio_id=s.id, cliente_id=cliente.id, criado_em=momento))
            db.session.commit()
            mesmo = do_apto is not None and do_apto.cliente_id == cliente.id
            session[chave_sessao] = {'nome': nome.split(' ')[0].capitalize(),
                                     'ja': 'eu' if mesmo else ('apto' if do_apto else '')}
            return redirect(url_for('sorteio_publico.pagina', codigo=s.codigo))

    inscrito = session.get(chave_sessao)
    resp = render_template('loja/sorteio.html', empresa=emp, s=s, situacao=situacao, erro=erro, form=form,
                           inscrito=inscrito, foto=_foto(s), fim=quando(s.fim), inicio=quando(s.inicio),
                           fim_iso=s.fim.isoformat(), agora_iso=momento.isoformat(),
                           ganhador=nome_publico(s.ganhador.cliente) if s.ganhador else None,
                           total=len(s.inscricoes))
    return resp, (400 if erro else 200)


# ---------------------------------------------------------------- administração (com login)

def _ler_form(s):
    """Preenche o sorteio com o formulário. Devolve a mensagem de erro (ou None)."""
    premio = re.sub(r'\s+', ' ', request.form.get('premio', '')).strip()[:120]
    descricao = re.sub(r'[ \t]+', ' ', request.form.get('descricao', '')).strip()[:300] or None
    try:
        inicio = datetime.strptime(request.form.get('inicio', ''), '%Y-%m-%dT%H:%M')
        fim = datetime.strptime(request.form.get('fim', ''), '%Y-%m-%dT%H:%M')
    except ValueError:
        return 'Informe quando as inscrições começam e terminam.'
    pid = request.form.get('produto_id', type=int)
    qtd = request.form.get('quantidade', type=int) or 1
    if not premio:
        return 'Informe o prêmio.'
    if fim <= inicio:
        return 'O fim das inscrições precisa ser depois do começo.'
    if not 1 <= qtd <= 50:
        return 'Quantidade do prêmio: de 1 a 50.'
    pid = pid if pid and db.session.get(Produto, pid) else None
    if s.ganhador and (pid, qtd) != (s.produto_id, s.quantidade or 1):
        return 'O sorteio já foi feito: o produto do prêmio não pode mais mudar.'
    s.premio, s.descricao, s.inicio, s.fim = premio, descricao, inicio, fim
    s.produto_id, s.quantidade = pid, qtd
    return None


def reserva_ativa(s):
    b = s.baixa
    return b if b is not None and b.estornada_em is None else None


def devolver_premio(s):
    """Estorna a baixa do prêmio: as unidades voltam para o estoque (sorteio excluído ou produto trocado)."""
    b = reserva_ativa(s)
    if b is not None:
        from app.precificacao import registrar_entrada
        registrar_entrada(b.produto, b.quantidade, b.custo_unitario or b.produto.custo or 0)
        b.estornada_em = agora()
    s.baixa = None


def reservar_premio(s):
    """Tira o prêmio do estoque como brinde (some do PDV e da loja). Devolve o erro se não houver estoque livre."""
    if s.produto_id is None:
        return None
    from app.loja import estoque_livre
    prod = Produto.query.filter_by(id=s.produto_id).with_for_update().one()
    livre = estoque_livre()(prod)
    if livre < s.quantidade:
        return (f'{prod.nome}: só tem {livre} unidade(s) livre(s) no estoque (descontados os pedidos em aberto). '
                f'O prêmio precisa de {s.quantidade}.')
    prod.quantidade = (prod.quantidade or 0) - s.quantidade
    g = s.ganhador
    b = BaixaEstoque(data=agora(), produto_id=prod.id, quantidade=s.quantidade, custo_unitario=round(prod.custo or 0, 4),
                     motivo='brinde', observacao=f'Prêmio do sorteio: {s.premio}'[:255],
                     cliente_id=g.cliente_id if g else None,
                     usuario_id=current_user.id if current_user.is_authenticated else None)
    db.session.add(b)
    s.baixa = b
    return None


@bp.route('/')
def lista():
    momento = agora()
    sorteios = Sorteio.query.order_by(Sorteio.fim.desc()).all()
    return render_template('sorteios.html', sorteios=sorteios, momento=momento, SITUACAO=SITUACAO)


@bp.route('/novo', methods=['GET', 'POST'])
@bp.route('/<int:id>/editar', methods=['GET', 'POST'])
def editar(id=None):
    s = db.session.get(Sorteio, id) if id else None
    if id and s is None:
        abort(404)
    if request.method == 'POST':
        novo = s is None
        if novo:
            s = Sorteio(codigo=secrets.token_urlsafe(6), criado_em=datetime.now())
        antes = (s.produto_id, s.quantidade or 1) if not novo and reserva_ativa(s) else None
        erro = _ler_form(s)
        if not erro and antes != (s.produto_id, s.quantidade or 1):
            # produto/quantidade mudou (ou é novo): devolve a reserva antiga e reserva de novo
            devolver_premio(s)
            db.session.flush()
            erro = reservar_premio(s)
        if erro:
            flash(erro, 'danger')
            db.session.rollback()
            if novo:
                s = None                    # a tela volta com o que foi digitado (request.form)
        else:
            if novo:
                db.session.add(s)
            db.session.commit()
            flash(f'Sorteio "{s.premio}" salvo.', 'success')
            return redirect(url_for('sorteios.ver', id=s.id))
    momento = agora().replace(second=0, microsecond=0)
    padrao = {'inicio': momento, 'fim': (momento + timedelta(days=1)).replace(hour=18, minute=0)}
    from app.loja import estoque_livre
    livre = estoque_livre()
    produtos = [(p, livre(p)) for p in Produto.query.filter(Produto.quantidade > 0).order_by(Produto.nome).all()]
    produtos = [(p, n) for p, n in produtos if n > 0 or (s is not None and p.id == s.produto_id)]
    if s is not None and s.produto is not None and s.produto not in [p for p, _ in produtos]:
        produtos.insert(0, (s.produto, livre(s.produto)))
    return render_template('sorteio_form.html', s=s, padrao=padrao, produtos=produtos, form=request.form,
                           reservado=reserva_ativa(s) if s else None)


@bp.route('/<int:id>')
def ver(id):
    s = db.session.get(Sorteio, id) or abort(404)
    momento = agora()
    link = link_publico(url_for('sorteio_publico.pagina', codigo=s.codigo))
    novos = sum(1 for i in s.inscricoes if i.cliente.origem == 'sorteio' and i.cliente.criado_em >= s.criado_em)
    return render_template('sorteio_ver.html', s=s, reserva=reserva_ativa(s), situacao=s.situacao(momento), SITUACAO=SITUACAO, link=link,
                           fim=quando(s.fim), inicio=quando(s.inicio), novos=novos, foto=_foto(s),
                           nome_publico=nome_publico, empresa=Empresa.atual())


@bp.route('/<int:id>/sortear', methods=['POST'])
def sortear(id):
    """Tira um inscrito ao acaso (entre os que ainda não foram tirados). Se as inscrições ainda estavam abertas,
    elas fecham agora. 'Sortear de novo' (o ganhador não respondeu) tira outro."""
    s = Sorteio.query.filter_by(id=id).with_for_update().first() or abort(404)
    momento = agora()
    if momento < s.inicio:
        return jsonify(erro='As inscrições deste sorteio ainda nem começaram.'), 400
    restantes = [i for i in s.inscricoes if not i.sorteado_em]
    if not restantes:
        return jsonify(erro='Não há mais inscritos para sortear.'), 400
    if s.fim > momento:
        s.fim = momento.replace(microsecond=0)
    escolhido = secrets.SystemRandom().choice(restantes)
    escolhido.sorteado_em = momento
    if reserva_ativa(s):
        s.baixa.cliente_id = escolhido.cliente_id      # a baixa do brinde fica no nome de quem ganhou
    db.session.commit()
    c = escolhido.cliente
    return jsonify(ok=True, id=escolhido.id, nome=c.nome, endereco=c.endereco, whatsapp=c.whatsapp or '',
                   publico=nome_publico(c), vez=len(s.sorteados))


@bp.route('/<int:id>/excluir', methods=['POST'])
def excluir(id):
    s = db.session.get(Sorteio, id) or abort(404)
    volta = ''
    if not s.ganhador and reserva_ativa(s):           # ninguém ganhou: o prêmio volta para o estoque
        volta = f' {s.baixa.quantidade} × {s.baixa.produto.nome} voltou para o estoque.'
        devolver_premio(s)
    db.session.delete(s)
    db.session.commit()
    flash(f'Sorteio "{s.premio}" excluído.{volta} Os clientes cadastrados por ele continuam na lista de clientes.', 'success')
    return redirect(url_for('sorteios.lista'))


@bp.route('/<int:id>/inscricao/<int:iid>/remover', methods=['POST'])
def remover_inscricao(id, iid):
    i = SorteioInscricao.query.filter_by(id=iid, sorteio_id=id).first_or_404()
    nome = i.cliente.nome
    db.session.delete(i)
    db.session.commit()
    flash(f'{nome} saiu deste sorteio (o cadastro de cliente continua).', 'success')
    return redirect(url_for('sorteios.ver', id=id))
