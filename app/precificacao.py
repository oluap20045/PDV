"""Sugestão de preço e custo médio.

Preço sugerido = custo médio / (1 - margem - taxa máxima do cartão)
  - a taxa do cartão incide sobre o PREÇO, por isso entra no divisor (não somada ao custo);
  - usa a maior taxa cadastrada: em qualquer forma de pagamento a margem fica >= a desejada;
  - MEI não tem imposto por venda (DAS é fixo), então não entra aqui.
"""
import math

from app.models import Empresa, TaxaPagamento


def taxa_maxima():
    """(percentual, descrição) da maior taxa cadastrada; (0, None) se não houver."""
    t = TaxaPagamento.query.order_by(TaxaPagamento.percentual.desc()).first()
    if t is None:
        return 0.0, None
    return t.percentual, f'{t.bandeira or "qualquer bandeira"} · {t.modalidade}'


def parametros():
    """Tudo que a tela precisa para calcular a sugestão no navegador."""
    taxa, desc = taxa_maxima()
    return {'margem': Empresa.atual().margem_lucro, 'taxa': taxa, 'taxa_desc': desc}


def preco_sugerido(custo, margem, taxa):
    """Arredonda para cima nos 10 centavos. None se não der para calcular."""
    divisor = 1 - (margem + taxa) / 100
    if not custo or custo <= 0 or divisor <= 0.05:
        return None
    return math.ceil(round(custo / divisor * 10, 6)) / 10


def registrar_entrada(produto, quantidade, custo_unitario):
    """Entrada no estoque atualizando o custo médio ponderado."""
    atual = max(produto.quantidade or 0, 0)
    if atual > 0 and (produto.custo or 0) > 0:
        produto.custo = round((atual * produto.custo + quantidade * custo_unitario) / (atual + quantidade), 4)
    else:
        produto.custo = custo_unitario
    produto.quantidade = (produto.quantidade or 0) + quantidade
