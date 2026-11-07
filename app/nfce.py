"""Leitura de NFC-e (cupom fiscal) pela URL do QR Code — por enquanto só Paraná.

Mesma lógica do capivara-financas: só consulta domínios oficiais da Sefaz (allowlist,
evita SSRF) e extrai estabelecimento, CNPJ, itens, total e chave de acesso da página.
"""
import re
import urllib.request
from datetime import datetime
from urllib.parse import urlparse

from bs4 import BeautifulSoup

DOMINIOS_PERMITIDOS = {
    'PR': {'www.fazenda.pr.gov.br', 'fazenda.pr.gov.br'},
}

# conteúdo "cru" do QR: chave(44)|versão|ambiente|id|hash(40)
RE_CODIGO_QRCODE = re.compile(r'^(\d{44})\|(\d)\|(\d)\|(\d)\|([0-9a-fA-F]{40})$')


class NfceErro(Exception):
    """Erro com mensagem pronta para mostrar ao usuário."""


def _normalizar_entrada(entrada):
    limpo = re.sub(r'\s+', '', entrada or '')
    if RE_CODIGO_QRCODE.match(limpo):
        return f'http://www.fazenda.pr.gov.br/nfce/qrcode?p={limpo}'
    if len(re.sub(r'\D', '', limpo)) == 44 and '://' not in limpo:
        raise NfceErro('Só a chave de acesso (44 dígitos) não basta — a Sefaz-PR exige o código completo do QR Code. '
                       'Leia o QR pela câmera ou cole a URL inteira.')
    return limpo


def _validar_url(entrada):
    url = _normalizar_entrada(entrada)
    partes = urlparse(url)
    if partes.scheme not in ('http', 'https') or not partes.hostname:
        raise NfceErro('Isso não parece a URL do QR Code de uma NFC-e.')
    host = partes.hostname.lower()
    estado = next((uf for uf, hosts in DOMINIOS_PERMITIDOS.items() if host in hosts), None)
    if not estado:
        raise NfceErro('Por enquanto só leio notas do Paraná (fazenda.pr.gov.br).')
    return url, estado


def valor_br(texto):
    """'1.234,56' -> 1234.56"""
    limpo = re.sub(r'[^\d,.-]', '', texto or '')
    limpo = re.sub(r'\.(?=\d{3}(?:\D|$))', '', limpo).replace(',', '.')
    try:
        return float(limpo)
    except ValueError:
        return 0.0


def _texto(el):
    return el.get_text(' ', strip=True) if el else ''


def parsear_pr(html, url_origem):
    soup = BeautifulSoup(html, 'html.parser')
    estabelecimento = _texto(soup.find(id='u20'))
    if not estabelecimento:
        raise NfceErro('Não consegui ler a nota. Confira a URL e se a consulta ainda está disponível na Sefaz.')

    cnpj = ''
    for el in soup.select('.text'):
        t = _texto(el)
        if 'CNPJ' in t.upper():
            m = re.search(r'[\d./-]{14,}', t)
            if m:
                cnpj = re.sub(r'\D', '', m.group(0))
                break

    itens = []
    tabela = soup.find(id='tabResult')
    for tr in (tabela.find_all('tr') if tabela else []):
        descricao = _texto(tr.select_one('.txtTit2'))
        if not descricao:
            continue
        m = re.search(r'\d+', _texto(tr.select_one('.RCod')))
        itens.append({
            'codigo': m.group(0) if m else '',
            'descricao': descricao,
            'quantidade': valor_br(re.sub(r'Qtde\.?:?', '', _texto(tr.select_one('.Rqtd')), flags=re.I)),
            'unidade': re.sub(r'^\s*UN:\s*', '', _texto(tr.select_one('.RUN')), flags=re.I).strip(),
            'valor_unitario': valor_br(re.sub(r'Vl\.?\s*Unit\.?:?', '', _texto(tr.select_one('.RvlUnit')), flags=re.I)),
            'valor_total': valor_br(_texto(tr.select_one('.valor'))),
        })
    if not itens:
        raise NfceErro('Nota encontrada, mas nenhum item foi reconhecido nela.')

    total = valor_br(_texto(soup.select_one('#totalNota .linhaShade .totalNumb')))
    forma = None
    linha_forma = soup.find(id='linhaForma')
    if linha_forma:
        prox = linha_forma.find_next_sibling('div')
        forma = _texto(prox.find('label')) if prox else None
        forma = re.sub(r'\s+\d+$', '', forma or '') or None   # "Cartão de Débito 2" -> "Cartão de Débito"

    chave = re.sub(r'\D', '', _texto(soup.select_one('.chave'))) or None
    infos = _texto(soup.find(id='infos'))
    m_emissao = re.search(r'Emiss[aã]o:\s*(\d{2}/\d{2}/\d{4}\s+\d{2}:\d{2}:\d{2})', infos)
    m_numero = re.search(r'N[úu]mero:\s*(\d+)', infos)
    data = datetime.strptime(m_emissao.group(1), '%d/%m/%Y %H:%M:%S') if m_emissao else None

    itens = juntar_itens(itens)
    soma_itens = round(sum(i['valor_total'] for i in itens), 2)
    total = total or soma_itens
    desconto = round(max(soma_itens - total, 0), 2)
    # custo real de cada item = valor do item com o desconto da nota rateado proporcionalmente
    fator = (total / soma_itens) if soma_itens else 1
    for it in itens:
        it['custo_total'] = round(it['valor_total'] * fator, 2)

    return {
        'estabelecimento': estabelecimento,
        'cnpj': cnpj,
        'numero': m_numero.group(1) if m_numero else None,
        'data_compra': data.isoformat() if data else None,
        'valor_total': total,
        'valor_itens': soma_itens,
        'desconto': desconto,
        'forma_pagamento': forma,
        'chave_acesso': chave if chave and len(chave) == 44 else None,
        'url_origem': url_origem,
        'itens': itens,
    }


def juntar_itens(itens):
    """A nota repete o mesmo produto em várias linhas; junta por código (ou descrição)."""
    juntos = {}
    for it in itens:
        chave = it['codigo'] or it['descricao']
        if chave in juntos:
            j = juntos[chave]
            j['quantidade'] = round(j['quantidade'] + it['quantidade'], 4)
            j['valor_total'] = round(j['valor_total'] + it['valor_total'], 2)
        else:
            juntos[chave] = dict(it)
    for j in juntos.values():
        if j['quantidade']:
            j['valor_unitario'] = round(j['valor_total'] / j['quantidade'], 4)
    return list(juntos.values())


PARSERS = {'PR': parsear_pr}


def buscar_nfce(entrada, timeout=20):
    url, estado = _validar_url(entrada)
    req = urllib.request.Request(url, headers={
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            # redirecionamento também precisa terminar num domínio oficial
            if (urlparse(resp.geturl()).hostname or '').lower() not in DOMINIOS_PERMITIDOS[estado]:
                raise NfceErro('A Sefaz redirecionou para um endereço inesperado; nota não lida.')
            html = resp.read().decode(resp.headers.get_content_charset() or 'utf-8', errors='replace')
    except NfceErro:
        raise
    except Exception as e:  # rede, timeout, HTTP 5xx...
        raise NfceErro(f'Não consegui consultar a Sefaz agora ({e}). Tente de novo em instantes.')
    dados = PARSERS[estado](html, url)
    dados['estado'] = estado
    return dados
