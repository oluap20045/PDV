"""Catálogo do fornecedor (revista Cacau Show): extrai código/nome/preço do PDF ou lê a planilha
revisada, e compara com o cadastro para criar produtos novos e atualizar preços.

Regra de ouro: só entra marcado o que é certeza. Preço que vale para grupo, preço em outra página,
nome não encontrado ou variação de preço grande vão como "dúvida" (desmarcados) para o usuário decidir.
"""
import csv
import io
import re

from app import db
from app.models import Produto

RE_CODIGO = re.compile(r'(?<!\d)(\d{7})(?!\d)')
RE_VALOR = re.compile(r'^\d{1,4},\d{2}$')
RE_PESO = re.compile(r'(\d+[.,]?\d*\s*(?:g|kg|ml|l)\b)\s*\|', re.I)
VARIACAO_SUSPEITA = 0.40      # preço mudou mais que 40%? pede conferência


# ---------------------------------------------------------------- PDF
def _spans(pagina):
    vistos, saida = set(), []
    for bloco in pagina.get_text('dict')['blocks']:
        for linha in bloco.get('lines', []):
            for s in linha['spans']:
                t = s['text'].strip()
                chave = (round(s['bbox'][0]), round(s['bbox'][1]), t)
                if t and chave not in vistos:      # o PDF repete trechos sobrepostos
                    vistos.add(chave)
                    saida.append({'t': t, 'x': s['bbox'][0], 'y': s['bbox'][1], 'x1': s['bbox'][2],
                                  'sz': s['size'], 'f': s['font']})
    return saida


def _pagina(spans, num):
    codigos = {}
    for s in spans:
        if s['sz'] > 8.5 or 'Light' not in s['f']:
            continue
        m = RE_CODIGO.search(s['t'])
        if not m or m.group(1) in codigos:
            continue
        vizinhos = [o for o in spans if abs(o['y'] - s['y']) < 2 and s['x'] - 45 < o['x'] <= s['x'] and o['sz'] <= 8.5]
        linha = ' '.join(o['t'] for o in sorted(vizinhos, key=lambda o: o['x']))
        if s['t'] != linha and s['t'] not in linha:
            linha += ' ' + s['t']
        peso = RE_PESO.search(linha)
        codigos[m.group(1)] = {'codigo': m.group(1), 'x': min(o['x'] for o in vizinhos), 'y': s['y'],
                               'peso': peso.group(1).strip() if peso else '', 'pagina': num}

    precos = []
    for s in spans:
        if RE_VALOR.match(s['t']) and 'Bold' in s['f'] and 11 <= s['sz'] <= 20:
            rs = [o for o in spans if o['t'] == 'R$' and abs(o['y'] - s['y']) < 6 and 0 < s['x'] - o['x'] < 25]
            if rs and not any(abs(p['x'] - rs[0]['x']) < 2 and abs(p['y'] - s['y']) < 2 for p in precos):
                precos.append({'v': float(s['t'].replace(',', '.')), 'x': rs[0]['x'], 'y': s['y']})

    nomes = [s for s in spans if 'Sagona' in s['f'] and 'Bold' in s['f'] and 8 <= s['sz'] <= 10.5 and len(s['t']) > 1]
    for c in codigos.values():
        linhas = sorted({(round(n['y']), n['t']) for n in nomes if abs(n['x'] - c['x']) < 4 and 0 < n['y'] - c['y'] < 30})
        partes, ult = [], c['y']
        for y, t in linhas:
            if y - ult < 13 and t not in partes:
                partes.append(t)
                ult = y
        c['nome'] = ' '.join(partes)
        # certeza: preço logo abaixo, mesma coluna, sem outro código no meio
        mesma_coluna = lambda o: abs(o['x'] - c['x']) < 6
        cand = [p for p in precos if mesma_coluna(p) and 0 < p['y'] - c['y'] < 100
                and not any(o is not c and mesma_coluna(o) and c['y'] < o['y'] < p['y'] for o in codigos.values())]
        # preço ACIMA na mesma coluna, sem outro preço no meio, é cabeçalho de lista ("R$ 11,99 cada" + códigos): não é certeza
        acima = [p for p in precos if mesma_coluna(p) and 0 < c['y'] - p['y'] < 220]
        if cand and not acima:
            p = min(cand, key=lambda p: p['y'])
            c['preco'], c['certeza'] = p['v'], True
            p['usado'] = True
        else:
            c['preco'], c['certeza'] = None, False
    # sem certeza: palpite = preço de grupo (o único que sobrou na página) ou o mais próximo
    livres = [p for p in precos if not p.get('usado')] or precos
    for c in codigos.values():
        if not c['certeza'] and livres:
            perto = min(livres, key=lambda p: abs(p['y'] - c['y']) + abs(p['x'] - c['x']))
            c['preco'] = perto['v']
            c['obs'] = ('preço do grupo da página' if len(livres) == 1 else 'preço mais próximo na página') + ' — confira'
    return list(codigos.values())


def extrair_pdf(dados_pdf):
    """Lê o PDF da revista e devolve [{codigo, nome, peso, preco, certeza, pagina}]."""
    import pymupdf
    itens = {}
    with pymupdf.open(stream=dados_pdf, filetype='pdf') as doc:
        for num, pagina in enumerate(doc, 1):
            for it in _pagina(_spans(pagina), num):
                atual = itens.get(it['codigo'])
                # o mesmo código aparece em mais de uma página: fica a leitura certa; se duas certas divergem, dúvida
                if atual is None or (it['certeza'] and not atual['certeza']):
                    itens[it['codigo']] = it
                elif it['certeza'] and atual['certeza'] and abs(it['preco'] - atual['preco']) > 0.009:
                    atual['certeza'] = False
                    atual['obs'] = f'preços diferentes nas páginas {atual["pagina"]} e {it["pagina"]}'
    for it in itens.values():
        it.pop('x', None), it.pop('y', None)
        it['categoria'] = ''
    return list(itens.values())


# ---------------------------------------------------------------- planilha
COLUNAS = ['codigo', 'nome', 'peso', 'preco', 'categoria']


def _num(valor):
    if valor is None or valor == '':
        return None
    if isinstance(valor, (int, float)):
        return float(valor)
    t = re.sub(r'[^\d,.-]', '', str(valor))
    if ',' in t:
        t = t.replace('.', '').replace(',', '.')
    try:
        return float(t)
    except ValueError:
        return None


def ler_planilha(nome_arquivo, dados):
    """xlsx ou csv (; ou ,) com cabeçalho: Código, Nome, Peso, Preço, Categoria (outras colunas são ignoradas)."""
    if nome_arquivo.lower().endswith('.xlsx'):
        import openpyxl
        wb = openpyxl.load_workbook(io.BytesIO(dados), read_only=True, data_only=True)
        linhas = [list(r) for r in wb.worksheets[0].iter_rows(values_only=True)]
    else:
        texto = dados.decode('utf-8-sig', errors='replace')
        dialeto = ';' if texto.split('\n', 1)[0].count(';') >= texto.split('\n', 1)[0].count(',') else ','
        linhas = list(csv.reader(io.StringIO(texto), delimiter=dialeto))
    if not linhas:
        raise ValueError('Planilha vazia.')

    def chave(c):
        c = str(c or '').strip().lower()
        for de, para in (('código', 'codigo'), ('preço', 'preco')):
            c = c.replace(de, para)
        return c.split()[0] if c else ''
    cab = [chave(c) for c in linhas[0]]
    if 'codigo' not in cab or 'preco' not in cab:
        raise ValueError('A planilha precisa das colunas "Código" e "Preço" na primeira linha.')
    itens = []
    for linha in linhas[1:]:
        reg = {c: (linha[i] if i < len(linha) else None) for i, c in enumerate(cab) if c in COLUNAS}
        codigo = re.sub(r'\D', '', str(reg.get('codigo') or '').split('.')[0])
        if not codigo:
            continue
        itens.append({'codigo': codigo, 'nome': str(reg.get('nome') or '').strip(),
                      'peso': str(reg.get('peso') or '').strip(), 'preco': _num(reg.get('preco')),
                      'categoria': str(reg.get('categoria') or '').strip(), 'certeza': True, 'pagina': None})
    return itens


# ---------------------------------------------------------------- comparação com o cadastro
def nome_completo(nome, peso):
    nome = re.sub(r'\s+', ' ', nome or '').strip()
    if peso and peso.lower().replace(' ', '') not in nome.lower().replace(' ', ''):
        nome = f'{nome} {peso}'
    return nome[:100]


def comparar(itens):
    """Classifica cada item: atualizar, novo, igual ou duvida (com motivo). 'marcado' = aplica por padrão."""
    por_codigo = {p.codigo_fornecedor: p for p in Produto.query.filter(Produto.codigo_fornecedor.isnot(None))}
    por_nome = {p.nome.lower(): p for p in Produto.query.all()}
    nomes_usados = set(por_nome)
    saida = []
    for it in itens:
        r = dict(it, nome_final=nome_completo(it.get('nome'), it.get('peso')), produto_id=None,
                 preco_atual=None, acao='duvida', motivo='', marcado=False)
        prod = por_codigo.get(it['codigo'])
        vinculo_por_nome = False
        if prod is None and r['nome_final'] and r['nome_final'].lower() in por_nome:
            prod, vinculo_por_nome = por_nome[r['nome_final'].lower()], True
            if prod.codigo_fornecedor:     # mesmo nome, mas é outro código: não mistura
                prod, vinculo_por_nome = None, False
        preco = it.get('preco')

        if prod is not None:
            r['produto_id'], r['preco_atual'], r['nome_final'] = prod.id, prod.preco, prod.nome
            if preco is None or preco <= 0:
                r['motivo'] = it.get('obs') or 'preço não encontrado na revista'
            elif abs(preco - prod.preco) < 0.005 and not vinculo_por_nome:
                r['acao'], r['motivo'] = 'igual', 'preço já é esse'
                r['marcado'] = False
            elif not it.get('certeza'):
                r['motivo'] = it.get('obs') or 'preço não está logo abaixo do código (grupo/promoção/outra página)'
            elif prod.preco and abs(preco - prod.preco) / prod.preco > VARIACAO_SUSPEITA:
                r['acao'], r['motivo'] = 'atualizar', f'mudou mais de {int(VARIACAO_SUSPEITA * 100)}% — confira'
            else:
                r['acao'], r['marcado'] = 'atualizar', True
                if vinculo_por_nome:
                    r['motivo'] = 'achado pelo nome; vai gravar o código do catálogo'
        else:
            if preco is None or preco <= 0:
                r['motivo'] = it.get('obs') or 'preço não encontrado na revista'
            elif not it.get('nome'):
                r['motivo'] = 'nome não encontrado (só aparece na foto) — digite o nome'
                r['acao'] = 'novo'
            elif not it.get('certeza'):
                r['acao'], r['motivo'] = 'novo', it.get('obs') or 'preço não está logo abaixo do código — confira'
            else:
                r['acao'], r['marcado'] = 'novo', True
            if r['nome_final'] and r['nome_final'].lower() in nomes_usados:
                r['nome_final'] = f'{r["nome_final"][:90]} ({it["codigo"]})'
            nomes_usados.add((r['nome_final'] or '').lower())
        saida.append(r)
    ordem = {'atualizar': 0, 'novo': 1, 'duvida': 2, 'igual': 3}
    saida.sort(key=lambda r: (ordem[r['acao']], not r['marcado'], r.get('pagina') or 0, r['nome_final'] or ''))
    return saida


def aplicar(itens, form):
    """Grava só as linhas marcadas. Devolve (criados, atualizados)."""
    criados = atualizados = 0
    for i, it in enumerate(itens):
        if form.get(f'ok_{i}') != '1':
            continue
        preco = _num(form.get(f'preco_{i}'))
        nome = (form.get(f'nome_{i}') or '').strip()[:100]
        if not preco or preco <= 0:
            raise ValueError(f'Preço inválido em "{nome or it["codigo"]}".')
        prod = db.session.get(Produto, it['produto_id']) if it.get('produto_id') else \
            Produto.query.filter_by(codigo_fornecedor=it['codigo']).first()
        if prod is not None:
            prod.preco = round(preco, 2)
            if not prod.codigo_fornecedor:
                prod.codigo_fornecedor = it['codigo']
            if it.get('categoria') and not prod.categoria:
                prod.categoria = it['categoria'][:60]
            atualizados += 1
        else:
            if not nome:
                raise ValueError(f'Digite o nome do produto de código {it["codigo"]}.')
            if Produto.query.filter(db.func.lower(Produto.nome) == nome.lower()).first():
                nome = f'{nome[:90]} ({it["codigo"]})'
            db.session.add(Produto(nome=nome, preco=round(preco, 2), custo=0, quantidade=0, estoque_minimo=0,
                                   codigo_fornecedor=it['codigo'], categoria=(it.get('categoria') or None)))
            criados += 1
        db.session.flush()
    db.session.commit()
    return criados, atualizados


def _serializer():
    from flask import current_app
    from itsdangerous import URLSafeSerializer
    return URLSafeSerializer(current_app.config['SECRET_KEY'], salt='catalogo')


CAMPOS_TOKEN = ('codigo', 'nome_final', 'peso', 'preco', 'categoria', 'produto_id', 'acao', 'pagina')


def assinar(itens):
    return _serializer().dumps([{k: it.get(k) for k in CAMPOS_TOKEN} for it in itens])


def ler_assinado(token):
    from itsdangerous import BadSignature
    try:
        return _serializer().loads(token)
    except BadSignature:
        return None
