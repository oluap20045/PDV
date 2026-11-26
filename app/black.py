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
    """Como fica cada produto COM ESTOQUE (o que a tela mostra) e quantos produtos do cadastro mudam."""
    taxa, desc = taxa_maxima()
    emp = Empresa.atual()
    linhas, muda = [], 0
    for p in Produto.query.filter(Produto.custo > 0).order_by(Produto.nome):
        normal = p.preco_normal or p.preco
        black = (p.preco if p.preco_normal else None) if emp.black_ativo else preco_black(p.custo, normal, margem, taxa)
        if black is None:
            continue
        muda += 1
        if (p.quantidade or 0) > 0:
            linhas.append({'nome': p.nome, 'custo': p.custo, 'normal': normal, 'black': black,
                           'pct': round(100 * (1 - black / normal)) if normal else 0, 'qtd': p.quantidade})
    return {'linhas': linhas, 'muda': muda, 'taxa': taxa, 'taxa_desc': desc}


def desligar():
    n = 0
    for p in Produto.query.filter(Produto.preco_normal.isnot(None)):
        p.preco, p.preco_normal = p.preco_normal, None
        n += 1
    Empresa.atual().black_ativo = False
    return n


def ligar(margem):
    """(Re)liga com a margem dada: devolve os preços normais primeiro, então dá para recalcular com a Black ligada."""
    desligar()
    taxa, _ = taxa_maxima()
    n = 0
    for p in Produto.query.filter(Produto.custo > 0):
        novo = preco_black(p.custo, p.preco, margem, taxa)
        if novo is not None:
            p.preco_normal, p.preco = p.preco, novo
            n += 1
    emp = Empresa.atual()
    emp.black_ativo, emp.black_margem = True, margem
    return n
