# Local: app/routes.py

# ALTERAÇÃO INÍCIO - Linhas 1 a 8
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, Response, abort
from app import db
from app.models import Produto, Venda, ItemVenda
from app.models import GrupoConta, Conta, Lancamento, Fornecedor 
from app.models import Compra, CompraItem, Cliente
from app.models import NOME_CONTA_VENDAS, FORMAS_PAGAMENTO, FORMA_A_PRAZO
from app.models import (NOME_CONTA_TAXAS, FORMAS_CARTAO, FORMA_CREDITO, BANDEIRAS, MAX_PARCELAS,
                        TaxaPagamento, VendaPagamento, Empresa)
from urllib.parse import quote
from app.precificacao import registrar_entrada, parametros as parametros_preco
import re
# Crie um Blueprint chamado 'main'
bp = Blueprint('main', __name__)


def _conta_de_vendas():
    """Conta usada nos recebimentos de venda; recria se alguém tiver apagado."""
    conta = Conta.query.filter_by(nome=NOME_CONTA_VENDAS).first()
    if conta is None:
        grupo = GrupoConta.query.filter_by(nome='1. Receitas Operacionais').first()
        if grupo is None:
            grupo = GrupoConta(nome='1. Receitas Operacionais')
            db.session.add(grupo)
        conta = Conta(nome=NOME_CONTA_VENDAS, grupo=grupo)
        db.session.add(conta)
        db.session.flush()
    return conta


def _conta_por_nome(nome, grupo_nome):
    conta = Conta.query.filter_by(nome=nome).first()
    if conta is None:
        grupo = GrupoConta.query.filter_by(nome=grupo_nome).first()
        if grupo is None:
            grupo = GrupoConta(nome=grupo_nome)
            db.session.add(grupo)
        conta = Conta(nome=nome, grupo=grupo)
        db.session.add(conta)
        db.session.flush()
    return conta


def _pagamentos_do_form():
    """Linhas de pagamento do PDV (listas alinhadas pag_forma[], pag_valor[], pag_bandeira[], pag_parcelas[])."""
    formas = request.form.getlist('pag_forma[]')
    valores = request.form.getlist('pag_valor[]')
    bandeiras = request.form.getlist('pag_bandeira[]')
    parcelas = request.form.getlist('pag_parcelas[]')
    if not formas or not (len(formas) == len(valores) == len(bandeiras) == len(parcelas)):
        raise ValueError('Informe a forma de pagamento.')
    linhas = []
    for forma, valor, bandeira, parc in zip(formas, valores, bandeiras, parcelas):
        try:
            valor = valor.strip()
            if ',' in valor:
                valor = valor.replace('.', '').replace(',', '.')
            valor = round(float(valor), 2)
        except ValueError:
            raise ValueError('Valor de pagamento inválido.')
        if valor <= 0:
            continue   # linha vazia
        if forma not in FORMAS_PAGAMENTO:
            raise ValueError('Forma de pagamento inválida.')
        bandeira = bandeira if forma in FORMAS_CARTAO else None
        if forma in FORMAS_CARTAO and bandeira not in BANDEIRAS:
            raise ValueError(f'Escolha a bandeira do {forma.lower()}.')
        parc = int(parc) if forma == FORMA_CREDITO and parc.isdigit() else 1
        if not 1 <= parc <= MAX_PARCELAS:
            raise ValueError('Número de parcelas inválido.')
        linhas.append({'forma': forma, 'valor': valor, 'bandeira': bandeira, 'parcelas': parc})
    if not linhas:
        raise ValueError('Informe a forma de pagamento.')
    return linhas


def _lancar_pagamentos(venda, cliente, linhas, quando, vencimento_fiado):
    """Grava as formas de pagamento, o 'a receber' de cada uma e a despesa da taxa de cartão.
    Devolve (taxa_total, valor_no_fiado)."""
    conta_vendas = _conta_de_vendas()
    conta_taxas = None
    taxa_total = fiado = 0.0
    resumo = []
    for ln in linhas:
        pag = VendaPagamento(venda=venda, **ln)
        db.session.add(pag)
        a_prazo = ln['forma'] == FORMA_A_PRAZO
        pag.lancamento = Lancamento(
            descricao=f'Venda #{venda.id} - {cliente.nome} ({pag.descricao})'[:200],
            valor=ln['valor'], tipo='RECEBER', data_lancamento=quando,
            data_vencimento=vencimento_fiado if a_prazo else quando.date(),
            data_pagamento=None if a_prazo else quando, conta_id=conta_vendas.id)
        if a_prazo:
            fiado += ln['valor']

        taxa = TaxaPagamento.buscar(ln['forma'], ln['bandeira'], ln['parcelas'])
        if taxa and taxa.percentual > 0:
            pag.taxa_percentual = taxa.percentual
            pag.taxa_valor = round(ln['valor'] * taxa.percentual / 100, 2)
            conta_taxas = conta_taxas or _conta_por_nome(NOME_CONTA_TAXAS, '6. Despesas Comerciais')
            pag.lancamento_taxa = Lancamento(   # a maquininha já desconta: despesa nasce paga
                descricao=f'Taxa {pag.descricao} {taxa.percentual:.2f}%'.replace('.', ',')[:180] + f' - Venda #{venda.id}',
                valor=pag.taxa_valor, tipo='PAGAR', data_lancamento=quando, data_vencimento=quando.date(),
                data_pagamento=quando, conta_id=conta_taxas.id)
            taxa_total += pag.taxa_valor
        resumo.append(pag.descricao if len(linhas) == 1 else f'{pag.descricao} R$ {ln["valor"]:.2f}')
    venda.taxa_total = round(taxa_total, 2)
    venda.forma_pagamento = ' + '.join(resumo)[:120]
    return round(taxa_total, 2), round(fiado, 2)


def _codigo_barras_do_form():
    """Código de barras do formulário; vazio vira None (o campo é único, vários vazios não podem colidir)."""
    codigo = (request.form.get('codigo_barras') or '').strip()
    return codigo or None

@bp.route('/')
def index():
# ALTERAÇÃO FIM

    return redirect(url_for('main.venda_pdv'))

# Rota para Cadastro de Produtos
# ALTERAÇÃO: troque @app.route por @bp.route
@bp.route('/produtos', methods=['GET', 'POST'])
def produtos():
    # A correção está na indentação desta função inteira.
    # Certifique-se de que cada nível de indentação
    # use 4 espaços e não haja nenhum caractere TAB.
    if request.method == 'POST':
        nome = request.form['nome']
        preco = float(request.form['preco'])
        custo = float(request.form['custo'])
        quantidade = int(request.form['quantidade'])
        estoque_minimo = int(request.form['estoque_minimo'])
        codigo_barras = _codigo_barras_do_form()

        if codigo_barras and Produto.query.filter_by(codigo_barras=codigo_barras).first():
            flash(f'O código de barras {codigo_barras} já está cadastrado em outro produto.', 'danger')
            return redirect(url_for('main.produtos'))

        novo_produto = Produto(nome=nome, preco=preco, custo=custo, quantidade=quantidade,
                               estoque_minimo=estoque_minimo, codigo_barras=codigo_barras)
        db.session.add(novo_produto)
        db.session.commit()
        flash('Produto cadastrado com sucesso!', 'success')
        return redirect(url_for('main.produtos'))

    lista_produtos = Produto.query.all()
    from app.precificacao import preco_sugerido
    params = parametros_preco()
    sugestoes = {p.id: preco_sugerido(p.custo, params['margem'], params['taxa']) for p in lista_produtos}
    return render_template('produtos.html', produtos=lista_produtos, preco=params, sugestoes=sugestoes)

# Rota para Controle de Estoque
# ALTERAÇÃO: troque @app.route por @bp.route
@bp.route('/estoque')
def estoque():
    # Parâmetros da URL para busca e ordenação
    search_term = request.args.get('search', '')
    sort_by = request.args.get('sort_by', 'nome') # Padrão: ordenar por nome
    order = request.args.get('order', 'asc')     # Padrão: ascendente

    query = Produto.query

    # Aplicar filtro de busca se houver
    if search_term:
        query = query.filter(Produto.nome.ilike(f'%{search_term}%'))

    # Validar colunas permitidas para ordenação para segurança
    allowed_sort_columns = ['nome', 'quantidade', 'estoque_minimo']
    if sort_by not in allowed_sort_columns:
        sort_by = 'nome'

    # Aplicar ordenação
    if order == 'desc':
        query = query.order_by(getattr(Produto, sort_by).desc())
    else:
        query = query.order_by(getattr(Produto, sort_by).asc())

    lista_produtos = query.all()

    return render_template(
        'estoque.html',
        produtos=lista_produtos,
        search=search_term,
        sort_by=sort_by,
        order=order
    )

# Rota para a Tela de Venda (PDV)
# ALTERAÇÃO: troque @app.route por @bp.route
@bp.route('/venda', methods=['GET', 'POST'])
def venda_pdv():
    if request.method == 'POST':
        itens_carrinho = request.form.getlist('carrinho[]')
        
        if not itens_carrinho:
            flash('Carrinho vazio!', 'danger')
            # ALTERAÇÃO: adicione o prefixo do blueprint 'main.'
            return redirect(url_for('main.venda_pdv'))

        cliente = db.session.get(Cliente, request.form.get('cliente_id', type=int) or 0)
        if cliente is None:
            flash('Selecione o cliente antes de finalizar a venda.', 'danger')
            return redirect(url_for('main.venda_pdv'))

        data_da_venda = datetime.now(ZoneInfo("America/Sao_Paulo"))
        try:
            vencimento_fiado = datetime.strptime(request.form.get('data_vencimento', ''), '%Y-%m-%d').date()
        except ValueError:
            vencimento_fiado = data_da_venda.date() + timedelta(days=30)

        try:
            pagamentos = _pagamentos_do_form()
        except ValueError as e:
            flash(str(e), 'danger')
            return redirect(url_for('main.venda_pdv', cliente=cliente.id))
        if any(p['forma'] == FORMA_A_PRAZO for p in pagamentos) and cliente.padrao:
            flash('Venda no fiado precisa de um cliente identificado.', 'danger')
            return redirect(url_for('main.venda_pdv'))

        total_venda = 0
        nova_venda = Venda(total=0, data=data_da_venda, cliente_id=cliente.id, forma_pagamento='')
        db.session.add(nova_venda)
        db.session.flush()

        try:
            for item_str in itens_carrinho:
                produto_id, quantidade_vendida = item_str.split('|')
                quantidade_vendida = int(quantidade_vendida)
                produto = db.session.get(Produto, int(produto_id))
                if produto is None:
                    raise Exception('produto não encontrado')
                if produto.quantidade < quantidade_vendida:
                    raise Exception(f'Estoque insuficiente para o produto {produto.nome}')
                produto.quantidade -= quantidade_vendida
                total_venda += produto.preco * quantidade_vendida
                db.session.add(ItemVenda(
                    venda_id=nova_venda.id, produto_id=produto.id, quantidade=quantidade_vendida,
                    preco_unitario=produto.preco,
                    custo_unitario=produto.custo,   # custo do momento da venda
                ))
            total_venda = round(total_venda, 2)
            nova_venda.total = total_venda

            pago = round(sum(p['valor'] for p in pagamentos), 2)
            if abs(pago - total_venda) > 0.009:
                raise Exception(f'as formas de pagamento somam R$ {pago:.2f}, mas a venda é de R$ {total_venda:.2f}')

            taxa_total, fiado_total = _lancar_pagamentos(nova_venda, cliente, pagamentos, data_da_venda, vencimento_fiado)
            db.session.commit()

            msg = f'Venda #{nova_venda.id} de R$ {total_venda:.2f} para {cliente.nome} finalizada ({nova_venda.forma_pagamento})'
            if taxa_total:
                msg += f' — taxa de cartão R$ {taxa_total:.2f} lançada como despesa'
            if fiado_total:
                msg += f' — R$ {fiado_total:.2f} no fiado, a receber em {vencimento_fiado.strftime("%d/%m/%Y")}'
            flash(msg + '.', 'success')
            return redirect(url_for('main.venda_pdv', ultima=nova_venda.id))

        except Exception as e:
            db.session.rollback()
            flash(f'Erro ao processar a venda: {e}', 'danger')
            return redirect(url_for('main.venda_pdv', cliente=cliente.id))

        return redirect(url_for('main.venda_pdv'))

    produtos_disponiveis = Produto.query.filter(Produto.quantidade > 0).all()
    padrao = Cliente.padrao_do_sistema()
    clientes = Cliente.query.order_by(Cliente.padrao.desc(), Cliente.nome).all()
    # ?cliente=<id> vem de "novo cliente" a partir do PDV; senão, o padrão
    selecionado = request.args.get('cliente', type=int)
    if not any(c.id == selecionado for c in clientes):
        selecionado = padrao.id
    ultima = db.session.get(Venda, request.args.get('ultima', type=int) or 0)
    return render_template('venda.html', produtos=produtos_disponiveis, ultima=ultima,
                           clientes=clientes, cliente_selecionado=selecionado,
                           formas_pagamento=FORMAS_PAGAMENTO, forma_a_prazo=FORMA_A_PRAZO,
                           formas_cartao=FORMAS_CARTAO, forma_credito=FORMA_CREDITO,
                           bandeiras=BANDEIRAS, max_parcelas=MAX_PARCELAS,
                           taxas=[{'forma': t.forma, 'bandeira': t.bandeira, 'de': t.parcelas_de,
                                   'ate': t.parcelas_ate, 'pct': t.percentual} for t in TaxaPagamento.query.all()],
                           vencimento_padrao=(datetime.now(ZoneInfo("America/Sao_Paulo")).date()
                                              + timedelta(days=30)).isoformat())


@bp.route('/vendas')
def vendas_realizadas():
    # Parâmetros de paginação e filtro
    page = request.args.get('page', 1, type=int)
    data_inicio_str = request.args.get('data_inicio')
    data_fim_str = request.args.get('data_fim')

    # ALTERAÇÃO INÍCIO: Definir data de hoje como padrão
    if not data_inicio_str and not data_fim_str:
        # Força o uso do fuso horário de São Paulo para obter a data correta
        hoje = datetime.now(ZoneInfo("America/Sao_Paulo"))
        hoje_str = hoje.strftime('%Y-%m-%d')
        data_inicio_str = hoje_str
        data_fim_str = hoje_str
    # ALTERAÇÃO FIM

    query = Venda.query

    if data_inicio_str:
        data_inicio = datetime.strptime(data_inicio_str, '%Y-%m-%d').date()
        query = query.filter(Venda.data >= data_inicio)

    if data_fim_str:
        data_fim = datetime.strptime(data_fim_str, '%Y-%m-%d').date()
        query = query.filter(Venda.data < (data_fim + timedelta(days=1)))

    # Cálculo dos totais para TODO o período filtrado (antes da paginação)
    todas_as_vendas_do_periodo = query.all()
    total_vendido_periodo = sum(v.total for v in todas_as_vendas_do_periodo)
    taxas_periodo = sum(v.taxa_total or 0 for v in todas_as_vendas_do_periodo)
    lucro_total_periodo = sum(
        (item.preco_unitario - item.custo_unitario) * item.quantidade
        for venda in todas_as_vendas_do_periodo for item in venda.itens
    ) - taxas_periodo

    # ALTERAÇÃO INÍCIO: Aplicar paginação na query
    pagination = query.order_by(Venda.data.desc()).paginate(
        page=page, per_page=10, error_out=False
    )
    vendas_paginadas = pagination.items
    # ALTERAÇÃO FIM
    
    return render_template(
        'vendas.html',
        vendas=vendas_paginadas, # Envia a lista paginada
        pagination=pagination,    # Envia o objeto de paginação
        total_vendido=total_vendido_periodo,
        lucro_total=lucro_total_periodo,
        taxas_periodo=taxas_periodo,
        data_inicio=data_inicio_str,
        data_fim=data_fim_str
    )

@bp.route('/produto/edit/<int:id>', methods=['GET', 'POST'])
def editar_produto(id):
    # Busca o produto no banco de dados pelo ID, ou retorna erro 404 se não encontrar
    produto = Produto.query.get_or_404(id)

    if request.method == 'POST':
        # Se o formulário foi enviado (POST), atualiza os dados do produto
        produto.nome = request.form['nome']
        produto.preco = float(request.form['preco'])
        produto.custo = float(request.form['custo'])
        produto.quantidade = int(request.form['quantidade'])
        produto.estoque_minimo = int(request.form['estoque_minimo'])
        codigo_barras = _codigo_barras_do_form()
        if codigo_barras and Produto.query.filter(Produto.codigo_barras == codigo_barras,
                                                  Produto.id != produto.id).first():
            flash(f'O código de barras {codigo_barras} já está cadastrado em outro produto.', 'danger')
            return redirect(url_for('main.editar_produto', id=produto.id))
        produto.codigo_barras = codigo_barras
        db.session.commit()
        flash('Produto atualizado com sucesso!', 'success')
        return redirect(url_for('main.produtos'))
    
    # Se for o primeiro acesso (GET), exibe o formulário preenchido com os dados atuais
    return render_template('edit_produto.html', produto=produto, preco=parametros_preco())


@bp.route('/contas-e-grupos', methods=['GET', 'POST'])
def gerenciar_contas():
    if request.method == 'POST':
        # Verifica se está criando um grupo ou uma conta
        if 'nome_grupo' in request.form:
            nome = request.form['nome_grupo'].strip()
            if GrupoConta.query.filter_by(nome=nome).first():
                flash(f'Já existe o grupo "{nome}".', 'warning')
                return redirect(url_for('main.gerenciar_contas'))
            db.session.add(GrupoConta(nome=nome))
            flash('Grupo de conta criado com sucesso!', 'success')
        elif 'nome_conta' in request.form:
            nome = request.form['nome_conta'].strip()
            if Conta.query.filter_by(nome=nome).first():
                flash(f'Já existe a conta "{nome}".', 'warning')
                return redirect(url_for('main.gerenciar_contas'))
            if not request.form.get('grupo_id', type=int):
                flash('Escolha o grupo da conta.', 'warning')
                return redirect(url_for('main.gerenciar_contas'))
            db.session.add(Conta(nome=nome, grupo_id=request.form.get('grupo_id', type=int)))
            flash('Conta criada com sucesso!', 'success')
        
        db.session.commit()
        return redirect(url_for('main.gerenciar_contas'))

    grupos = GrupoConta.query.order_by(GrupoConta.nome).all()
    contas = Conta.query.order_by(Conta.nome).all()
    return render_template('contas_e_grupos.html', grupos=grupos, contas=contas)


@bp.route('/financeiro', methods=['GET', 'POST'])
def lancamentos():
    # Lógica de POST (criação de novo lançamento) continua a mesma
    if request.method == 'POST':
        descricao = request.form.get('descricao', '').strip()
        tipo = request.form.get('tipo')
        conta_id = request.form.get('conta_id', type=int)
        try:
            valor = float(request.form.get('valor', ''))
            vencimento = datetime.strptime(request.form.get('data_vencimento', ''), '%Y-%m-%d').date()
        except ValueError:
            valor = vencimento = None
        if not descricao or tipo not in ('PAGAR', 'RECEBER') or not conta_id or not db.session.get(Conta, conta_id) \
                or valor is None or valor <= 0 or vencimento is None:
            flash('Preencha descrição, valor, vencimento, conta e tipo.', 'danger')
            return redirect(url_for('main.lancamentos'))
        db.session.add(Lancamento(
            descricao=descricao, valor=valor, tipo=tipo, conta_id=conta_id,
            data_lancamento=datetime.now(ZoneInfo("America/Sao_Paulo")), data_vencimento=vencimento,
        ))
        db.session.commit()
        flash(f'Lançamento "{descricao}" criado com sucesso!', 'success')
        return redirect(url_for('main.lancamentos'))

    # --- LÓGICA DE FILTRO (GET) ---
    data_inicio_str = request.args.get('data_inicio')
    data_fim_str = request.args.get('data_fim')
    status_filtro = request.args.get('status', 'aberto') # Padrão: mostrar 'em aberto'
    tipo_filtro = request.args.get('tipo', 'todos') # Padrão: mostrar todos os tipos

    # Se nenhuma data for fornecida, define o mês atual como padrão
    if not data_inicio_str and not data_fim_str:
        hoje = datetime.now(ZoneInfo("America/Sao_Paulo"))
        primeiro_dia_mes = hoje.replace(day=1)
        # Lógica para encontrar o último dia do mês
        if hoje.month == 12:
            ultimo_dia_mes = hoje.replace(year=hoje.year + 1, month=1, day=1) - timedelta(days=1)
        else:
            ultimo_dia_mes = hoje.replace(month=hoje.month + 1, day=1) - timedelta(days=1)
        
        data_inicio_str = primeiro_dia_mes.strftime('%Y-%m-%d')
        data_fim_str = ultimo_dia_mes.strftime('%Y-%m-%d')

    # Inicia a query base
    query = Lancamento.query

    # Aplica filtro de data (usando data de vencimento)
    if data_inicio_str:
        data_inicio = datetime.strptime(data_inicio_str, '%Y-%m-%d').date()
        query = query.filter(Lancamento.data_vencimento >= data_inicio)
    if data_fim_str:
        data_fim = datetime.strptime(data_fim_str, '%Y-%m-%d').date()
        query = query.filter(Lancamento.data_vencimento <= data_fim)

    # Aplica filtro de status
    if status_filtro == 'aberto':
        query = query.filter(Lancamento.data_pagamento == None)
    elif status_filtro == 'quitado':
        query = query.filter(Lancamento.data_pagamento != None)

    # Aplica filtro de tipo (A Pagar / A Receber)
    if tipo_filtro == 'pagar':
        a_pagar = query.filter_by(tipo='PAGAR').order_by(Lancamento.data_vencimento).all()
        a_receber = [] # Se o filtro é 'pagar', a lista de receber é vazia
    elif tipo_filtro == 'receber':
        a_pagar = [] # Se o filtro é 'receber', a lista de pagar é vazia
        a_receber = query.filter_by(tipo='RECEBER').order_by(Lancamento.data_vencimento).all()
    else: # 'todos'
        a_pagar = query.filter_by(tipo='PAGAR').order_by(Lancamento.data_vencimento).all()
        a_receber = query.filter_by(tipo='RECEBER').order_by(Lancamento.data_vencimento).all()
    
    contas = Conta.query.order_by(Conta.nome).all()

    return render_template(
        'lancamentos.html', 
        contas=contas, 
        a_pagar=a_pagar, 
        a_receber=a_receber, 
        hoje=datetime.now(ZoneInfo("America/Sao_Paulo")).date(),
        # Envia os valores dos filtros de volta para o template
        data_inicio=data_inicio_str,
        data_fim=data_fim_str,
        status_filtro=status_filtro,
        tipo_filtro=tipo_filtro
    )


#Rota para EDITAR um lançamento
@bp.route('/lancamento/edit/<int:id>', methods=['GET', 'POST'])
def edit_lancamento(id):
    lancamento = Lancamento.query.get_or_404(id)
    contas = Conta.query.order_by(Conta.nome).all()

    if request.method == 'POST':
        lancamento.descricao = request.form['descricao']
        lancamento.valor = float(request.form['valor'])
        lancamento.tipo = request.form['tipo']
        lancamento.conta_id = int(request.form['conta_id'])
        lancamento.data_vencimento = datetime.strptime(request.form['data_vencimento'], '%Y-%m-%d').date()
        
        # Lógica para atualizar ou limpar a data de pagamento
        if request.form.get('data_pagamento'):
            lancamento.data_pagamento = datetime.strptime(request.form['data_pagamento'], '%Y-%m-%d')
        else:
            lancamento.data_pagamento = None
            
        db.session.commit()
        flash('Lançamento atualizado com sucesso!', 'success')
        return redirect(url_for('main.lancamentos'))

    return render_template('edit_lancamento.html', lancamento=lancamento, contas=contas)

# Rota para QUITAR (marcar como pago/recebido) um lançamento
@bp.route('/lancamento/quitar/<int:id>', methods=['POST'])
def quitar_lancamento(id):
    lancamento = Lancamento.query.get_or_404(id)
    # Define a data de pagamento com o fuso horário correto
    lancamento.data_pagamento = datetime.now(ZoneInfo("America/Sao_Paulo"))
    db.session.commit()
    status = "paga" if lancamento.tipo == 'PAGAR' else "recebida"
    flash(f'Conta "{lancamento.descricao}" marcada como {status}!', 'info')
    return redirect(url_for('main.lancamentos'))

@bp.route('/fornecedores', methods=['GET', 'POST'])
def fornecedores():
    if request.method == 'POST':
        novo_fornecedor = Fornecedor(nome=request.form['nome_fornecedor'])
        db.session.add(novo_fornecedor)
        db.session.commit()
        flash('Fornecedor cadastrado com sucesso!', 'success')
        return redirect(url_for('main.fornecedores'))
    
    lista_fornecedores = Fornecedor.query.order_by(Fornecedor.nome).all()
    return render_template('fornecedores.html', fornecedores=lista_fornecedores)


@bp.route('/compras')
def compras():
    # Parâmetros da URL
    page = request.args.get('page', 1, type=int)
    data_inicio_str = request.args.get('data_inicio')
    data_fim_str = request.args.get('data_fim')
    sort_by = request.args.get('sort_by', 'data_compra') # Padrão
    order = request.args.get('order', 'desc') # Padrão

    query = Compra.query

    # Filtro de Data
    if data_inicio_str:
        data_inicio = datetime.strptime(data_inicio_str, '%Y-%m-%d').date()
        query = query.filter(Compra.data_compra >= data_inicio)
    if data_fim_str:
        data_fim = datetime.strptime(data_fim_str, '%Y-%m-%d').date()
        # Adiciona 1 dia para incluir a data final no filtro
        query = query.filter(Compra.data_compra < (data_fim + timedelta(days=1)))

    # Lógica de Ordenação
    allowed_sort_columns = {
        'data_compra': Compra.data_compra,
        'fornecedor': Fornecedor.nome,
        'valor_total': Compra.valor_total,
        'data_vencimento': Compra.data_vencimento
    }
    
    if sort_by not in allowed_sort_columns:
        sort_by = 'data_compra'

    sort_column = allowed_sort_columns[sort_by]

    # Para ordenar por fornecedor, precisamos de um JOIN
    if sort_by == 'fornecedor':
        query = query.join(Fornecedor)

    if order == 'asc':
        query = query.order_by(sort_column.asc())
    else:
        query = query.order_by(sort_column.desc())

    # Paginação
    pagination = query.paginate(page=page, per_page=50, error_out=False)
    lista_compras = pagination.items

    return render_template(
        'compras.html',
        compras=lista_compras,
        pagination=pagination,
        data_inicio=data_inicio_str,
        data_fim=data_fim_str,
        sort_by=sort_by,
        order=order
    )




@bp.route('/compra/nova', methods=['GET', 'POST'])
def nova_compra():
    if request.method == 'POST':
        # --- Processar o formulário ---
        try:
            # 1. Pegar dados do cabeçalho de forma segura
            nota_fiscal = request.form.get('nota_fiscal', '') # '' como valor padrão
            data_vencimento_str = request.form.get('data_vencimento')
            fornecedor_id_str = request.form.get('fornecedor_id')
            conta_id_str = request.form.get('conta_id')

            # Validação básica para campos obrigatórios
            if not data_vencimento_str or not fornecedor_id_str or not conta_id_str:
                flash('Campos obrigatórios (vencimento, fornecedor, conta) não foram preenchidos.', 'danger')
                return redirect(url_for('main.nova_compra'))

            data_compra = datetime.now(ZoneInfo("America/Sao_Paulo"))
            data_vencimento = datetime.strptime(data_vencimento_str, '%Y-%m-%d').date()
            fornecedor_id = int(fornecedor_id_str)
            conta_id = int(conta_id_str)

            nova_compra_obj = Compra(
                nota_fiscal=nota_fiscal,
                data_compra=data_compra,
                data_vencimento=data_vencimento,
                fornecedor_id=fornecedor_id
            )
            db.session.add(nova_compra_obj)
            
            # 2. Processar os itens da compra
            total_compra = 0
            itens_form = request.form.getlist('produto_id')
            quantidades_form = request.form.getlist('quantidade')
            custos_form = request.form.getlist('custo')

            for i in range(len(itens_form)):
                produto_id = int(itens_form[i])
                quantidade = int(quantidades_form[i])
                custo = float(custos_form[i])
                
                # Cria o item da compra
                novo_item = CompraItem(
                    compra=nova_compra_obj,
                    produto_id=produto_id,
                    quantidade=quantidade,
                    custo_unitario=custo
                )
                db.session.add(novo_item)
                
                # Atualiza estoque e custo do produto
                produto = Produto.query.get(produto_id)
                registrar_entrada(produto, quantidade, custo)   # estoque + custo médio ponderado
                
                total_compra += quantidade * custo

            # 3. Atualiza o valor total na compra
            nova_compra_obj.valor_total = total_compra
            
            # 4. Gera o lançamento no contas a pagar
            novo_lancamento = Lancamento(
                descricao=f"Compra NF: {nota_fiscal}",
                valor=total_compra,
                tipo='PAGAR',
                data_lancamento=data_compra,
                data_vencimento=data_vencimento,
                conta_id=conta_id
            )
            db.session.add(novo_lancamento)
            db.session.flush() # Força o ID do lançamento a ser gerado

            # 5. Vincula o lançamento à compra
            nova_compra_obj.lancamento_id = novo_lancamento.id
            
            db.session.commit()
            flash('Compra lançada com sucesso e conta a pagar gerada!', 'success')
            return redirect(url_for('main.compras'))

        except Exception as e:
            db.session.rollback()
            flash(f'Erro ao processar a compra: {e}', 'danger')
            return redirect(url_for('main.nova_compra'))

    # --- Exibir o formulário (GET) ---
    fornecedores = Fornecedor.query.order_by(Fornecedor.nome).all()
    produtos = Produto.query.order_by(Produto.nome).all()
    todas_as_contas = Conta.query.join(GrupoConta).order_by(GrupoConta.nome, Conta.nome).all()
    
    produtos_js = [{'id': p.id, 'nome': p.nome} for p in produtos]
    return render_template('nova_compra.html', fornecedores=fornecedores, produtos=produtos, preco=parametros_preco(),
                           produtos_js=produtos_js, contas=todas_as_contas)


# ---------------------------------------------------------------- Clientes

def _so_digitos(valor):
    return re.sub(r'\D', '', valor or '')


def cpf_valido(cpf):
    """Confere os dois dígitos verificadores do CPF (só dígitos)."""
    if len(cpf) != 11 or cpf == cpf[0] * 11:
        return False
    for tam in (9, 10):
        soma = sum(int(cpf[i]) * (tam + 1 - i) for i in range(tam))
        dv = (soma * 10) % 11 % 10
        if dv != int(cpf[tam]):
            return False
    return True


def _cliente_do_form():
    """Lê e valida o formulário. Devolve (dados, erro)."""
    dados = {
        'nome': request.form.get('nome', '').strip(),
        'telefone': _so_digitos(request.form.get('telefone')) or None,
        'whatsapp': _so_digitos(request.form.get('whatsapp')) or None,
        'email': (request.form.get('email') or '').strip().lower() or None,
        'cpf': _so_digitos(request.form.get('cpf')) or None,
    }
    if not dados['nome']:
        return dados, 'Informe o nome do cliente.'
    if dados['cpf'] and not cpf_valido(dados['cpf']):
        return dados, 'CPF inválido — confira os números.'
    if dados['email'] and not re.fullmatch(r'[^@\s]+@[^@\s]+\.[^@\s]+', dados['email']):
        return dados, 'E-mail inválido.'
    return dados, None


@bp.app_template_filter('telefone')
def formatar_telefone(valor):
    d = _so_digitos(valor)
    if len(d) == 11:
        return f'({d[:2]}) {d[2:7]}-{d[7:]}'
    if len(d) == 10:
        return f'({d[:2]}) {d[2:6]}-{d[6:]}'
    return valor or ''


@bp.app_template_filter('cnpj')
def formatar_cnpj_filtro(valor):
    d = _so_digitos(valor)
    return f'{d[:2]}.{d[2:5]}.{d[5:8]}/{d[8:12]}-{d[12:]}' if len(d) == 14 else (valor or '')


@bp.app_template_filter('cpf')
def formatar_cpf(valor):
    d = _so_digitos(valor)
    return f'{d[:3]}.{d[3:6]}.{d[6:9]}-{d[9:]}' if len(d) == 11 else (valor or '')


@bp.route('/clientes', methods=['GET', 'POST'])
def clientes():
    if request.method == 'POST':
        dados, erro = _cliente_do_form()
        if not erro and dados['cpf'] and Cliente.query.filter_by(cpf=dados['cpf']).first():
            erro = 'Já existe um cliente com esse CPF.'
        if erro:
            flash(erro, 'danger')
            return render_template('clientes.html', clientes=_listar_clientes(),
                                   form=dict(dados, voltar=request.form.get('voltar')))
        novo = Cliente(**dados)
        db.session.add(novo)
        db.session.commit()
        flash(f'Cliente {dados["nome"]} cadastrado!', 'success')
        if request.form.get('voltar') == 'venda':   # veio do PDV: volta com ele selecionado
            return redirect(url_for('main.venda_pdv', cliente=novo.id))
        return redirect(url_for('main.clientes'))

    return render_template('clientes.html', clientes=_listar_clientes(), form={})


def _listar_clientes():
    busca = request.args.get('busca', '').strip()
    query = Cliente.query
    if busca:
        digitos = _so_digitos(busca)
        filtros = [Cliente.nome.ilike(f'%{busca}%'), Cliente.email.ilike(f'%{busca}%')]
        if digitos:
            filtros += [Cliente.cpf.contains(digitos), Cliente.telefone.contains(digitos),
                        Cliente.whatsapp.contains(digitos)]
        query = query.filter(db.or_(*filtros))
    return query.order_by(Cliente.nome).all()


@bp.route('/cliente/edit/<int:id>', methods=['GET', 'POST'])
def editar_cliente(id):
    cliente = Cliente.query.get_or_404(id)
    if request.method == 'POST':
        dados, erro = _cliente_do_form()
        if not erro and dados['cpf'] and Cliente.query.filter(Cliente.cpf == dados['cpf'],
                                                              Cliente.id != cliente.id).first():
            erro = 'Já existe outro cliente com esse CPF.'
        if erro:
            flash(erro, 'danger')
            return render_template('edit_cliente.html', cliente=cliente, form=dados)
        for campo, valor in dados.items():
            setattr(cliente, campo, valor)
        db.session.commit()
        flash('Cliente atualizado!', 'success')
        return redirect(url_for('main.clientes'))
    return render_template('edit_cliente.html', cliente=cliente, form=None)


# ---------------------------------------------------------------- Compra via NFC-e (QR Code do cupom)

@bp.route('/compras/nfce/ler', methods=['POST'])
def nfce_ler():
    from app.nfce import buscar_nfce, NfceErro
    from app.compras_nfce import preparar_previa, assinar
    entrada = (request.get_json(silent=True) or {}).get('url', '')
    if not entrada.strip():
        return jsonify(erro='Leia o QR Code ou cole a URL da nota.'), 400
    try:
        dados = buscar_nfce(entrada)
    except NfceErro as e:
        return jsonify(erro=str(e)), 400
    token = assinar(dados)   # o que volta no "confirmar" é exatamente o que a Sefaz devolveu
    previa = preparar_previa(dados)
    previa['token'] = token
    return jsonify(previa)


@bp.route('/compras/nfce/confirmar', methods=['POST'])
def nfce_confirmar():
    from app.compras_nfce import ler_assinado, confirmar
    dados = ler_assinado(request.form.get('token', ''))
    if not dados:
        flash('Nota inválida ou expirada — leia o QR Code de novo.', 'danger')
        return redirect(url_for('main.nova_compra'))
    try:
        compra, entraram, pago = confirmar(dados, request.form, datetime.now(ZoneInfo("America/Sao_Paulo")))
    except ValueError as e:
        db.session.rollback()
        flash(str(e), 'danger')
        return redirect(url_for('main.nova_compra'))
    situacao = 'já paga' if pago else 'em aberto no contas a pagar'
    flash(f'Compra importada: {entraram} produto(s) entraram no estoque; '
          f'R$ {compra.valor_total:.2f} lançado no financeiro ({situacao}).', 'success')
    return redirect(url_for('main.compras'))


# ---------------------------------------------------------------- Taxas de cartão

def _taxa_do_form():
    forma = request.form.get('forma')
    modalidade = request.form.get('modalidade')     # debito | credito_vista | credito_parcelado | pix
    bandeira = request.form.get('bandeira') or None
    try:
        pct = float((request.form.get('percentual') or '').replace(',', '.'))
    except ValueError:
        raise ValueError('Percentual inválido.')
    if not 0 <= pct < 100:
        raise ValueError('Percentual deve estar entre 0 e 100.')
    if bandeira and bandeira not in BANDEIRAS:
        raise ValueError('Bandeira inválida.')
    de = ate = 1
    if modalidade == 'debito':
        forma = FORMAS_CARTAO[0]
    elif modalidade == 'credito_vista':
        forma = FORMA_CREDITO
    elif modalidade == 'credito_parcelado':
        forma = FORMA_CREDITO
        de = request.form.get('parcelas_de', type=int) or 2
        ate = request.form.get('parcelas_ate', type=int) or MAX_PARCELAS
        if not 2 <= de <= ate <= MAX_PARCELAS:
            raise ValueError(f'Faixa de parcelas inválida (de 2 até {MAX_PARCELAS}).')
    elif modalidade == 'pix':
        forma, bandeira = FORMAS_PAGAMENTO[0], None
    else:
        raise ValueError('Escolha a modalidade.')
    return dict(forma=forma, bandeira=bandeira, parcelas_de=de, parcelas_ate=ate, percentual=pct)


def _taxa_conflitante(dados, ignorar_id=None):
    """Outra taxa da mesma forma/bandeira com faixa de parcelas que se sobrepõe."""
    q = TaxaPagamento.query.filter(
        TaxaPagamento.forma == dados['forma'],
        (TaxaPagamento.bandeira == dados['bandeira']) if dados['bandeira'] else TaxaPagamento.bandeira.is_(None),
        TaxaPagamento.parcelas_de <= dados['parcelas_ate'], TaxaPagamento.parcelas_ate >= dados['parcelas_de'])
    if ignorar_id:
        q = q.filter(TaxaPagamento.id != ignorar_id)
    return q.first()


@bp.route('/taxas', methods=['GET', 'POST'])
def taxas():
    if request.method == 'POST':
        try:
            dados = _taxa_do_form()
            conflito = _taxa_conflitante(dados)
            if conflito and (conflito.parcelas_de, conflito.parcelas_ate) != (dados['parcelas_de'], dados['parcelas_ate']):
                raise ValueError(f'Já existe {conflito.bandeira or "Qualquer bandeira"} · {conflito.modalidade}, '
                                 'que cobre parte dessas parcelas. Ajuste a faixa ou exclua a existente.')
            if conflito:
                conflito.percentual = dados['percentual']   # mesma combinação: atualiza em vez de duplicar
                msg = f'Taxa atualizada: {conflito.bandeira or "Qualquer bandeira"} · {conflito.modalidade} = {dados["percentual"]:.2f}%'
            else:
                t = TaxaPagamento(**dados)
                db.session.add(t)
                msg = f'Taxa cadastrada: {t.bandeira or "Qualquer bandeira"} · {t.modalidade} = {t.percentual:.2f}%'
            db.session.commit()
            flash(msg.replace('.', ','), 'success')
        except ValueError as e:
            flash(str(e), 'danger')
        return redirect(url_for('main.taxas'))

    lista = TaxaPagamento.query.all()
    ordem_forma = {f: i for i, f in enumerate(FORMAS_PAGAMENTO)}
    lista.sort(key=lambda t: (t.bandeira is None, t.bandeira or '', ordem_forma.get(t.forma, 9), t.parcelas_de))
    return render_template('taxas.html', taxas=lista, bandeiras=BANDEIRAS, max_parcelas=MAX_PARCELAS)


@bp.route('/taxa/<int:id>/excluir', methods=['POST'])
def excluir_taxa(id):
    t = TaxaPagamento.query.get_or_404(id)
    db.session.delete(t)
    db.session.commit()
    flash('Taxa excluída. Vendas já feitas mantêm a taxa da época.', 'info')
    return redirect(url_for('main.taxas'))


@bp.route('/taxa/<int:id>/editar', methods=['POST'])
def editar_taxa(id):
    t = TaxaPagamento.query.get_or_404(id)
    try:
        pct = float((request.form.get('percentual') or '').replace(',', '.'))
        if not 0 <= pct < 100:
            raise ValueError
    except ValueError:
        flash('Percentual inválido.', 'danger')
        return redirect(url_for('main.taxas'))
    t.percentual = pct
    db.session.commit()
    flash('Taxa atualizada.', 'success')
    return redirect(url_for('main.taxas'))


# ---------------------------------------------------------------- Comprovante (sem valor fiscal)

@bp.route('/empresa', methods=['GET', 'POST'])
def empresa():
    emp = Empresa.atual()
    if request.method == 'POST':
        nome = request.form.get('nome', '').strip()
        cnpj = _so_digitos(request.form.get('cnpj'))
        if not nome:
            flash('Informe o nome da empresa.', 'danger')
            return redirect(url_for('main.empresa'))
        if cnpj and len(cnpj) != 14:
            flash('CNPJ deve ter 14 dígitos.', 'danger')
            return redirect(url_for('main.empresa'))
        emp.nome = nome[:120]
        emp.cnpj = cnpj or None
        emp.telefone = _so_digitos(request.form.get('telefone')) or None
        emp.endereco = (request.form.get('endereco') or '').strip()[:200] or None
        emp.mensagem = (request.form.get('mensagem') or '').strip()[:200] or None
        try:
            margem = float((request.form.get('margem_lucro') or '30').replace(',', '.'))
        except ValueError:
            margem = -1
        if not 0 <= margem < 90:
            flash('Margem de lucro deve ficar entre 0 e 90%.', 'danger')
            return redirect(url_for('main.empresa'))
        emp.margem_lucro = margem
        db.session.commit()
        flash('Dados da empresa salvos — já aparecem nos comprovantes.', 'success')
        return redirect(url_for('main.empresa'))
    return render_template('empresa.html', empresa=emp, preco=parametros_preco())


@bp.route('/venda/<int:id>/comprovante.pdf')
def comprovante_pdf(id):
    from app.comprovante import gerar_pdf
    venda = Venda.query.get_or_404(id)
    pdf = gerar_pdf(venda, Empresa.atual())
    nome = f'comprovante-venda-{venda.id}.pdf'
    disposicao = 'attachment' if request.args.get('baixar') else 'inline'
    return Response(pdf, mimetype='application/pdf',
                    headers={'Content-Disposition': f'{disposicao}; filename="{nome}"'})


@bp.route('/venda/<int:id>/whatsapp')
def comprovante_whatsapp(id):
    """Abre o WhatsApp no número do cliente (se houver) com o resumo da compra."""
    from app.comprovante import texto_whatsapp
    venda = Venda.query.get_or_404(id)
    texto = quote(texto_whatsapp(venda, Empresa.atual()))
    numero = (venda.cliente.whatsapp or venda.cliente.telefone or '') if venda.cliente else ''
    numero = _so_digitos(numero)
    if numero and len(numero) in (10, 11):
        return redirect(f'https://wa.me/55{numero}?text={texto}')
    return redirect(f'https://wa.me/?text={texto}')   # sem número: o WhatsApp pede o contato
