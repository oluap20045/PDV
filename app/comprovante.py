"""Comprovante de venda (sem valor fiscal): PDF estilo cupom 80 mm e texto para WhatsApp."""
import re

from fpdf import FPDF

from app.models import FORMA_A_PRAZO

LARGURA = 80          # mm (bobina de 80 mm)
MARGEM = 4
UTIL = LARGURA - 2 * MARGEM

_TROCAS = {'—': '-', '–': '-', '•': '*', '“': '"', '”': '"', '‘': "'", '’': "'", '…': '...', '×': 'x'}


def _txt(texto):
    """Fonte padrão do PDF é latin-1: troca o que não cabe (acentos do português cabem)."""
    texto = ''.join(_TROCAS.get(c, c) for c in str(texto or ''))
    # emoji e afins não existem na fonte do PDF: some em vez de virar "?"
    return re.sub(r'(?<=\S) {2,}(?=\S)', ' ', texto.encode('latin-1', 'ignore').decode('latin-1')).rstrip()


def brl(valor):
    s = f'{valor:,.2f}'
    return 'R$ ' + s.replace(',', 'X').replace('.', ',').replace('X', '.')


def formatar_cnpj(cnpj):
    d = re.sub(r'\D', '', cnpj or '')
    return f'{d[:2]}.{d[2:5]}.{d[5:8]}/{d[8:12]}-{d[12:]}' if len(d) == 14 else (cnpj or '')


def formatar_cpf(cpf):
    d = re.sub(r'\D', '', cpf or '')
    return f'{d[:3]}.{d[3:6]}.{d[6:9]}-{d[9:]}' if len(d) == 11 else ''


def formatar_fone(fone):
    d = re.sub(r'\D', '', fone or '')
    if len(d) == 11:
        return f'({d[:2]}) {d[2:7]}-{d[7:]}'
    if len(d) == 10:
        return f'({d[:2]}) {d[2:6]}-{d[6:]}'
    return fone or ''


def _linhas_pagamento(venda):
    linhas = []
    for pg in venda.pagamentos:
        rotulo = pg.descricao
        if pg.forma == FORMA_A_PRAZO and pg.lancamento is not None:
            rotulo += f' (pagar até {pg.lancamento.data_vencimento.strftime("%d/%m/%Y")})'
        linhas.append((rotulo, pg.valor))
    return linhas


def _desenhar(pdf, venda, empresa):
    pdf.set_margins(MARGEM, MARGEM, MARGEM)
    pdf.add_page()

    def centro(texto, tam=8, estilo='', h=4):
        pdf.set_font('Helvetica', estilo, tam)
        pdf.multi_cell(UTIL, h, _txt(texto), align='C', new_x='LMARGIN', new_y='NEXT')

    def separador():
        pdf.ln(1)
        pdf.set_draw_color(120, 120, 120)
        pdf.dashed_line(MARGEM, pdf.get_y(), LARGURA - MARGEM, pdf.get_y(), 1, 1)
        pdf.ln(2)

    def par(esq, dir_, tam=8, estilo=''):
        pdf.set_font('Helvetica', estilo, tam)
        largura_dir = pdf.get_string_width(_txt(dir_)) + 1
        y = pdf.get_y()
        pdf.multi_cell(UTIL - largura_dir, 4, _txt(esq), new_x='LMARGIN', new_y='NEXT')
        y_fim = pdf.get_y()
        pdf.set_xy(LARGURA - MARGEM - largura_dir, y)
        pdf.cell(largura_dir, 4, _txt(dir_), align='R')
        pdf.set_y(max(y_fim, y + 4))

    # cabeçalho da empresa
    centro(empresa.nome, 11, 'B', 5)
    if empresa.cnpj:
        centro(f'CNPJ {formatar_cnpj(empresa.cnpj)}')
    if empresa.endereco:
        centro(empresa.endereco)
    if empresa.telefone:
        centro(f'Tel/WhatsApp {formatar_fone(empresa.telefone)}')
    separador()
    centro('COMPROVANTE DE VENDA', 9, 'B')
    centro('Documento sem valor fiscal', 7, 'I')
    separador()

    par(f'Venda nº {venda.id}', venda.data.strftime('%d/%m/%Y %H:%M'))
    cliente = venda.cliente
    if cliente and not cliente.padrao:
        texto = f'Cliente: {cliente.nome}'
        if cliente.cpf:
            texto += f'  CPF {formatar_cpf(cliente.cpf)}'
        pdf.set_font('Helvetica', '', 8)
        pdf.multi_cell(UTIL, 4, _txt(texto), new_x='LMARGIN', new_y='NEXT')
    separador()

    # itens
    for item in venda.itens:
        pdf.set_font('Helvetica', 'B', 8)
        pdf.multi_cell(UTIL, 4, _txt(item.produto.nome if item.produto else 'Produto'), new_x='LMARGIN', new_y='NEXT')
        par(f'  {item.quantidade} x {brl(item.preco_unitario)}', brl(item.quantidade * item.preco_unitario))
    separador()

    par('TOTAL', brl(venda.total), 11, 'B')
    pdf.ln(1)
    pdf.set_font('Helvetica', 'B', 8)
    pdf.cell(UTIL, 4, _txt('Pagamento'), new_x='LMARGIN', new_y='NEXT')
    for rotulo, valor in _linhas_pagamento(venda):
        par(f'  {rotulo}', brl(valor))
    separador()

    if empresa.mensagem:
        centro(empresa.mensagem, 8, 'B')
    centro('Documento sem valor fiscal', 6, 'I', 3)


def gerar_pdf(venda, empresa):
    """Duas passadas: mede a altura do cupom e gera a página no tamanho certo."""
    rascunho = FPDF(unit='mm', format=(LARGURA, 1000))
    rascunho.set_auto_page_break(False)
    _desenhar(rascunho, venda, empresa)
    altura = rascunho.get_y() + MARGEM + 2

    pdf = FPDF(unit='mm', format=(LARGURA, max(altura, 60)))
    pdf.set_auto_page_break(False)
    pdf.set_title(_txt(f'Comprovante venda {venda.id} - {empresa.nome}'))
    pdf.set_author(_txt(empresa.nome))
    _desenhar(pdf, venda, empresa)
    return bytes(pdf.output())


def texto_whatsapp(venda, empresa):
    """Resumo da compra para mandar no WhatsApp (negrito com *...*)."""
    cliente = venda.cliente
    saudacao = f'Olá, {cliente.nome.split()[0]}!' if cliente and not cliente.padrao else 'Olá!'
    linhas = [f'{saudacao} Segue o comprovante da sua compra na *{empresa.nome}* 🍫', '',
              f'*Venda nº {venda.id}* — {venda.data.strftime("%d/%m/%Y %H:%M")}']
    for item in venda.itens:
        nome = item.produto.nome if item.produto else 'Produto'
        linhas.append(f'• {item.quantidade}x {nome} — {brl(item.quantidade * item.preco_unitario)}')
    linhas += ['', f'*Total: {brl(venda.total)}*']
    for rotulo, valor in _linhas_pagamento(venda):
        linhas.append(f'Pagamento: {rotulo} — {brl(valor)}' if len(venda.pagamentos) > 1 else f'Pagamento: {rotulo}')
    if empresa.mensagem:
        linhas += ['', empresa.mensagem]
    linhas.append('_Documento sem valor fiscal_')
    return '\n'.join(linhas)
