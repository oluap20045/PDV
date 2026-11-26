"""Black Friday: um botão que põe o cadastro inteiro a quase preço de custo e depois devolve tudo.

Ligar:    preço = custo / (1 - (margem Black + MAIOR taxa de cartão))  -> arredonda para cima nos 10 centavos
          (a taxa incide sobre o preço, então qualquer forma de pagamento cobre o custo + a margem).
          O preço de tabela fica guardado em Produto.preco_normal. Só baixa preço, nunca sobe.
          Como muda o próprio preço de tabela, vale no PDV, na loja e nos pedidos sem mexer em mais nada.
Desligar: preco_normal volta para preco.
"""
from app import db
from app.models import Empresa, Produto
from app.precificacao import preco_sugerido, taxa_maxima

MARGEM_PADRAO = 5.0


def preco_black(custo, preco_atual, margem, taxa):
    """Preço Black do produto; None se não houver custo ou se não ficar mais barato que o atual."""
    novo = preco_sugerido(custo, margem, taxa)
    if novo is None or novo >= round(preco_atual or 0, 2) - 0.004:
        return None
    return round(novo, 2)


def previa(margem):
    """Linhas da tela: produtos COM ESTOQUE (dá para tirar da Black ou pôr um preço manual, ex.: 0,01 para chamar atenção).
    Produto sem estoque não aparece: segue a fórmula (se chegar estoque durante a Black, já entra com preço Black)."""
    taxa, desc = taxa_maxima()
    emp = Empresa.atual()
    linhas, fora = [], 0
    for p in Produto.query.order_by(Produto.nome):
        normal = p.preco_normal or p.preco
        auto = preco_black(p.custo, normal, margem, taxa)
        if (p.quantidade or 0) > 0:
            manual = None
            if emp.black_ativo and p.preco_normal:
                # preço diferente do que a fórmula daria na margem em uso = foi digitado à mão
                usado = preco_black(p.custo, normal, emp.black_margem, taxa)
                if usado is None or abs(p.preco - usado) > 0.004:
                    manual = p.preco
            linhas.append({'id': p.id, 'nome': p.nome, 'custo': p.custo or 0, 'normal': normal, 'auto': auto, 'qtd': p.quantidade,
                           'incluido': bool(p.preco_normal) if emp.black_ativo else True, 'manual': manual})
        elif auto is not None:
            fora += 1
    return {'linhas': linhas, 'fora': fora, 'taxa': taxa, 'taxa_desc': desc}


def desligar():
    n = 0
    for p in Produto.query.filter(Produto.preco_normal.isnot(None)):
        p.preco, p.preco_normal = p.preco_normal, None
        n += 1
    Empresa.atual().black_ativo = False
    return n


def ligar(margem, escolhas=None):
    """(Re)liga com a margem dada: devolve os preços normais primeiro, então dá para recalcular com a Black ligada.
    escolhas = {produto_id: False (fica fora) | float (preço manual) | None (fórmula)}; quem não está lá segue a fórmula."""
    escolhas = escolhas or {}
    desligar()
    taxa, _ = taxa_maxima()
    n = 0
    for p in Produto.query:
        e = escolhas.get(p.id)
        if e is False:
            continue
        if isinstance(e, float):
            novo = round(e, 2) if 0 < e < round(p.preco, 2) - 0.004 else None
        else:
            novo = preco_black(p.custo, p.preco, margem, taxa)
        if novo is not None:
            p.preco_normal, p.preco = p.preco, novo
            n += 1
    emp = Empresa.atual()
    emp.black_ativo, emp.black_margem = True, margem
    return n
