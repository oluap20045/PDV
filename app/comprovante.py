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

    # itens (combo "4 por 12" sai como um item só, com os produtos escolhidos embaixo)
    from app.combos import agrupar
    for bloco in agrupar(venda.itens):
        if bloco[0] == 'combo':
            _, combo, itens, total = bloco
            pdf.set_font('Helvetica', 'B', 8)
            pdf.multi_cell(UTIL, 4, _txt(f'Combo {combo.nome}' if combo else 'Combo'), new_x='LMARGIN', new_y='NEXT')
            pdf.set_font('Helvetica', '', 7)
            for it in itens:
                pdf.multi_cell(UTIL, 3.5, _txt(f'  {it.quantidade} x {it.produto.nome if it.produto else "Produto"}'),
                               new_x='LMARGIN', new_y='NEXT')
            par(f'  1 x {brl(total)}', brl(total))
            continue
        item = bloco[1]
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
    from app.combos import agrupar
    for bloco in agrupar(venda.itens):
        if bloco[0] == 'combo':
            _, combo, itens, total = bloco
            escolhidos = ', '.join(f'{it.quantidade}x {it.produto.nome if it.produto else "Produto"}' for it in itens)
            linhas.append(f'• 🎁 Combo {combo.nome if combo else ""} ({escolhidos}) — {brl(total)}')
            continue
        item = bloco[1]
        nome = item.produto.nome if item.produto else 'Produto'
        linhas.append(f'• {item.quantidade}x {nome} — {brl(item.quantidade * item.preco_unitario)}')
    linhas += ['', f'*Total: {brl(venda.total)}*']
    for rotulo, valor in _linhas_pagamento(venda):
        linhas.append(f'Pagamento: {rotulo} — {brl(valor)}' if len(venda.pagamentos) > 1 else f'Pagamento: {rotulo}')
    if empresa.mensagem:
        linhas += ['', empresa.mensagem]
    linhas.append('_Documento sem valor fiscal_')
    return '\n'.join(linhas)


# ---------------------------------------------------------------- Ordem de compra (para o fornecedor)

def gerar_pdf_ordem(ordem, empresa):
    """Pedido de compra em A4: código do fornecedor, produto e quantidade."""
    pdf = FPDF(unit='mm', format='A4')
    pdf.set_auto_page_break(True, 15)
    pdf.set_margins(15, 15, 15)
    pdf.set_title(_txt(f'Pedido de compra {ordem.id} - {empresa.nome}'))
    pdf.set_author(_txt(empresa.nome))
    pdf.add_page()
    largura = 180

    pdf.set_font('Helvetica', 'B', 14)
    pdf.cell(largura, 7, _txt(empresa.nome), new_x='LMARGIN', new_y='NEXT')
    pdf.set_font('Helvetica', '', 9)
    dados = []
    if empresa.cnpj:
        dados.append(f'CNPJ {formatar_cnpj(empresa.cnpj)}')
    if empresa.telefone:
        dados.append(f'Tel/WhatsApp {formatar_fone(empresa.telefone)}')
    if dados:
        pdf.cell(largura, 5, _txt('   '.join(dados)), new_x='LMARGIN', new_y='NEXT')
    if empresa.endereco:
        pdf.multi_cell(largura, 5, _txt(empresa.endereco), new_x='LMARGIN', new_y='NEXT')
    pdf.ln(4)

    pdf.set_font('Helvetica', 'B', 13)
    pdf.cell(largura / 2, 8, _txt(f'PEDIDO DE COMPRA Nº {ordem.id}'))
    pdf.set_font('Helvetica', '', 10)
    pdf.cell(largura / 2, 8, _txt(ordem.criado_em.strftime('%d/%m/%Y')), align='R', new_x='LMARGIN', new_y='NEXT')
    if ordem.fornecedor:
        f = ordem.fornecedor
        texto = f'Fornecedor: {f.nome}'
        if f.contato:
            texto += f'  (A/C {f.contato})'
        pdf.cell(largura, 6, _txt(texto), new_x='LMARGIN', new_y='NEXT')
    pdf.ln(3)

    # tabela
    col = (32, 123, 25)
    pdf.set_fill_color(235, 235, 235)
    pdf.set_font('Helvetica', 'B', 10)
    for w, t, a in zip(col, ('Código', 'Produto', 'Qtd'), ('L', 'L', 'R')):
        pdf.cell(w, 8, _txt(t), border=1, align=a, fill=True)
    pdf.ln()
    pdf.set_font('Helvetica', '', 10)
    total = 0
    for it in ordem.itens:
        p = it.produto
        codigo = p.codigo_fornecedor or p.codigo_barras or '-'
        nome = _txt(p.nome)
        # nome longo: quebra a linha da tabela inteira na mesma altura
        linhas = max(1, len(pdf.multi_cell(col[1], 6, nome, dry_run=True, output='LINES')))
        h = 6 * linhas
        if pdf.get_y() + h > pdf.h - 20:
            pdf.add_page()
        x, y = pdf.get_x(), pdf.get_y()
        pdf.cell(col[0], h, _txt(codigo), border=1)
        pdf.multi_cell(col[1], 6, nome, border=1, new_x='RIGHT', new_y='TOP', max_line_height=6)
        pdf.set_xy(x + col[0] + col[1], y)
        pdf.cell(col[2], h, str(it.quantidade), border=1, align='R')
        pdf.set_xy(x, y + h)
        total += it.quantidade
    pdf.set_font('Helvetica', 'B', 10)
    pdf.cell(col[0] + col[1], 8, _txt(f'{len(ordem.itens)} produto(s)'), border=1)
    pdf.cell(col[2], 8, str(total), border=1, align='R', new_x='LMARGIN', new_y='NEXT')

    if ordem.observacao:
        pdf.ln(4)
        pdf.set_font('Helvetica', 'B', 10)
        pdf.cell(largura, 6, _txt('Observação'), new_x='LMARGIN', new_y='NEXT')
        pdf.set_font('Helvetica', '', 10)
        pdf.multi_cell(largura, 5, _txt(ordem.observacao), new_x='LMARGIN', new_y='NEXT')
    return bytes(pdf.output())


def texto_whatsapp_ordem(ordem, empresa):
    f = ordem.fornecedor
    saudacao = f'Olá, {f.contato.split()[0]}!' if f and f.contato else 'Olá!'
    linhas = [f'{saudacao} Segue o pedido de compra da *{empresa.nome}*:', '',
              f'*Pedido de compra nº {ordem.id}* — {ordem.criado_em.strftime("%d/%m/%Y")}']
    for it in ordem.itens:
        p = it.produto
        codigo = p.codigo_fornecedor or p.codigo_barras
        linhas.append(f'• {it.quantidade}x {codigo + " - " if codigo else ""}{p.nome}')
    linhas += ['', f'Total: {sum(i.quantidade for i in ordem.itens)} unidade(s) em {len(ordem.itens)} produto(s)']
    if ordem.observacao:
        linhas += ['', f'Obs.: {ordem.observacao}']
    linhas += ['', 'Pode confirmar a disponibilidade e o prazo? Obrigado!']
    return '\n'.join(linhas)
