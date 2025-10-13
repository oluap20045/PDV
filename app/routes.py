# Local: app/routes.py

# ALTERAÇÃO INÍCIO - Linhas 1 a 8
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from flask import Blueprint, render_template, request, redirect, url_for, flash
from app import db
from app.models import Produto, Venda, ItemVenda
from app.models import GrupoConta, Conta, Lancamento

# Crie um Blueprint chamado 'main'
bp = Blueprint('main', __name__)

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
        
        novo_produto = Produto(nome=nome, preco=preco, custo=custo, quantidade=quantidade)
        db.session.add(novo_produto)
        db.session.commit()
        flash('Produto cadastrado com sucesso!', 'success')
        return redirect(url_for('main.produtos'))

    lista_produtos = Produto.query.all()
    return render_template('produtos.html', produtos=lista_produtos)

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

        total_venda = 0
        data_da_venda = datetime.now(ZoneInfo("America/Sao_Paulo"))
        nova_venda = Venda(total=0, data=data_da_venda)
        db.session.add(nova_venda)
        db.session.flush()

        try:
            for item_str in itens_carrinho:
                produto_id, quantidade_vendida = item_str.split('|')
                quantidade_vendida = int(quantidade_vendida)
                
                produto = Produto.query.get(produto_id)
                if produto.quantidade >= quantidade_vendida:
                    produto.quantidade -= quantidade_vendida
                    preco_item = produto.preco * quantidade_vendida
                    total_venda += preco_item
                    
                    # ALTERAÇÃO INÍCIO: Adicionar 'custo_unitario'
                    item_venda = ItemVenda(
                        venda_id=nova_venda.id,
                        produto_id=produto.id,
                        quantidade=quantidade_vendida,
                        preco_unitario=produto.preco,
                        custo_unitario=produto.custo  # <- Salva o custo atual do produto
                    )
                    # ALTERAÇÃO FIM
                    db.session.add(item_venda)
                else:
                    raise Exception(f'Estoque insuficiente para o produto {produto.nome}')

            nova_venda.total = total_venda
            db.session.commit()
            flash(f'Venda de R$ {total_venda:.2f} finalizada com sucesso!', 'success')

        except Exception as e:
            db.session.rollback()
            flash(f'Erro ao processar a venda: {e}', 'danger')

        # ALTERAÇÃO: adicione o prefixo do blueprint 'main.'
        return redirect(url_for('main.venda_pdv'))

    produtos_disponiveis = Produto.query.filter(Produto.quantidade > 0).all()
    return render_template('venda.html', produtos=produtos_disponiveis)


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
    lucro_total_periodo = sum(
        (item.preco_unitario - item.custo_unitario) * item.quantidade
        for venda in todas_as_vendas_do_periodo for item in venda.itens
    )

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
        db.session.commit()
        flash('Produto atualizado com sucesso!', 'success')
        return redirect(url_for('main.produtos'))
    
    # Se for o primeiro acesso (GET), exibe o formulário preenchido com os dados atuais
    return render_template('edit_produto.html', produto=produto)


@bp.route('/contas-e-grupos', methods=['GET', 'POST'])
def gerenciar_contas():
    if request.method == 'POST':
        # Verifica se está criando um grupo ou uma conta
        if 'nome_grupo' in request.form:
            novo_grupo = GrupoConta(nome=request.form['nome_grupo'])
            db.session.add(novo_grupo)
            flash('Grupo de conta criado com sucesso!', 'success')
        elif 'nome_conta' in request.form:
            nova_conta = Conta(nome=request.form['nome_conta'], grupo_id=request.form['grupo_id'])
            db.session.add(nova_conta)
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
        # ... (código para adicionar novo lançamento, sem alterações aqui) ...
        # ...
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
