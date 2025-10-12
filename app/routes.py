# Local: app/routes.py

# ALTERAÇÃO INÍCIO - Linhas 1 a 8
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from flask import Blueprint, render_template, request, redirect, url_for, flash
from app import db
from app.models import Produto, Venda, ItemVenda

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
