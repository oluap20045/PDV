"""Fluxo de caixa a partir dos lançamentos.

Realizado = pago/recebido, na data do pagamento. Previsto = em aberto, na data de vencimento;
o que já venceu e não foi pago conta como previsto para HOJE (dinheiro que ainda deve entrar/sair).
Saldo = saldo inicial da empresa + tudo que foi realizado até a data (+ previstos, daqui pra frente).
"""
from collections import OrderedDict
from datetime import date, timedelta

from app.models import Empresa, Lancamento

GRANULARIDADES = {'dia': 'Por dia', 'semana': 'Por semana', 'mes': 'Por mês'}
MESES = ['jan', 'fev', 'mar', 'abr', 'mai', 'jun', 'jul', 'ago', 'set', 'out', 'nov', 'dez']


def granularidade_auto(inicio, fim):
    dias = (fim - inicio).days + 1
    return 'dia' if dias <= 31 else ('semana' if dias <= 120 else 'mes')


def _chave(d, gran):
    if gran == 'dia':
        return d
    if gran == 'semana':
        return d - timedelta(days=d.weekday())        # segunda-feira
    return d.replace(day=1)


def _rotulo(k, gran, inicio, fim):
    if gran == 'dia':
        return k.strftime('%d/%m')
    if gran == 'semana':
        de, ate = max(k, inicio), min(k + timedelta(days=6), fim)
        return de.strftime('%d/%m') if de == ate else f'{de.strftime("%d/%m")}–{ate.strftime("%d/%m")}'
    return f'{MESES[k.month - 1]}/{k.strftime("%y")}'


def _proximo(k, gran):
    if gran == 'dia':
        return k + timedelta(days=1)
    if gran == 'semana':
        return k + timedelta(days=7)
    return (k.replace(day=28) + timedelta(days=4)).replace(day=1)


def calcular(inicio, fim, gran, hoje):
    empresa = Empresa.atual()
    saldo_base = empresa.saldo_inicial or 0.0

    periodos = OrderedDict()
    k = _chave(inicio, gran)
    while k <= fim:
        periodos[k] = {'rotulo': _rotulo(k, gran, inicio, fim), 'inicio': max(k, inicio),
                       'ent_real': 0.0, 'sai_real': 0.0, 'ent_prev': 0.0, 'sai_prev': 0.0, 'futuro': k > hoje,
                       'contem_hoje': max(k, inicio) <= hoje < _proximo(k, gran)}
        k = _proximo(k, gran)

    saldo_antes = saldo_base          # saldo no início do período
    por_conta = {}
    atrasados = {'RECEBER': [0, 0.0], 'PAGAR': [0, 0.0]}
    saldo_hoje = saldo_base

    for l in Lancamento.query.all():
        sinal = 1 if l.tipo == 'RECEBER' else -1
        if l.data_pagamento is not None:
            quando, realizado = l.data_pagamento.date(), True
            if quando <= hoje:
                saldo_hoje += sinal * l.valor
        else:
            realizado = False
            quando = l.data_vencimento
            if quando < hoje:
                atrasados[l.tipo][0] += 1
                atrasados[l.tipo][1] += l.valor
                quando = hoje
        if quando < inicio:
            # antes do período: entra no saldo inicial (previsto só conta se o período começa no futuro)
            if realizado or quando >= hoje:
                saldo_antes += sinal * l.valor
            continue
        if quando > fim:
            continue
        p = periodos[_chave(quando, gran)]
        campo = ('ent_' if sinal > 0 else 'sai_') + ('real' if realizado else 'prev')
        p[campo] += l.valor

        c = por_conta.setdefault(l.conta_id, {'conta': l.conta.nome, 'grupo': l.conta.grupo.nome,
                                              'ent_real': 0.0, 'sai_real': 0.0, 'ent_prev': 0.0, 'sai_prev': 0.0})
        c[campo] += l.valor

    saldo = saldo_antes
    for p in periodos.values():
        p['entradas'] = round(p['ent_real'] + p['ent_prev'], 2)
        p['saidas'] = round(p['sai_real'] + p['sai_prev'], 2)
        p['resultado'] = round(p['entradas'] - p['saidas'], 2)
        saldo += p['resultado']
        p['saldo'] = round(saldo, 2)

    lista = list(periodos.values())
    tot = {c: round(sum(p[c] for p in lista), 2) for c in ('ent_real', 'sai_real', 'ent_prev', 'sai_prev')}
    menor = min(lista, key=lambda p: p['saldo']) if lista else None
    contas = sorted(por_conta.values(), key=lambda c: (c['ent_real'] + c['ent_prev'] == 0,
                                                       -(c['ent_real'] + c['ent_prev'] + c['sai_real'] + c['sai_prev'])))
    return {
        'periodos': lista, 'totais': tot, 'contas': contas,
        'saldo_inicial': round(saldo_antes, 2), 'saldo_final': round(saldo, 2),
        'saldo_hoje': round(saldo_hoje, 2), 'saldo_base': saldo_base, 'empresa': empresa,
        'menor': menor, 'atrasados': atrasados,
    }


def periodo_padrao(hoje):
    """Mês atual + próximo: mostra o que já aconteceu e o que vem por aí."""
    inicio = hoje.replace(day=1)
    fim = (_proximo(_proximo(inicio, 'mes'), 'mes')) - timedelta(days=1)
    return inicio, fim


def atalhos(hoje):
    mes = hoje.replace(day=1)
    fim_mes = _proximo(mes, 'mes') - timedelta(days=1)
    mes_ant = (mes - timedelta(days=1)).replace(day=1)
    return [
        ('Este mês', mes, fim_mes),
        ('Mês passado', mes_ant, mes - timedelta(days=1)),
        ('Próximos 30 dias', hoje, hoje + timedelta(days=29)),
        ('Próximos 90 dias', hoje, hoje + timedelta(days=89)),
        ('Este ano', date(hoje.year, 1, 1), date(hoje.year, 12, 31)),
    ]
