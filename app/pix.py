"""Pix "copia e cola" (BR Code estático, padrão EMV do Banco Central) e o QR Code em SVG."""
import re
import unicodedata


def _campo(id_, valor):
    return f'{id_}{len(valor):02d}{valor}'


def _crc16(texto):
    crc = 0xFFFF
    for byte in texto.encode('utf-8'):
        crc ^= byte << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) if crc & 0x8000 else (crc << 1)
            crc &= 0xFFFF
    return f'{crc:04X}'


def _limpo(texto, tamanho):
    """Sem acento, maiúsculo, só caracteres seguros: alguns apps de banco recusam o resto."""
    sem_acento = unicodedata.normalize('NFKD', texto or '').encode('ascii', 'ignore').decode()
    return re.sub(r'[^A-Z0-9 .-]', '', sem_acento.upper()).strip()[:tamanho]


def normalizar_chave(chave):
    """Telefone vira +55DDDNUMERO; CPF/CNPJ só dígitos; e-mail e chave aleatória ficam como estão."""
    chave = (chave or '').strip()
    if '@' in chave or re.fullmatch(r'[0-9a-fA-F-]{36}', chave):
        return chave.lower() if '@' in chave else chave
    digitos = re.sub(r'\D', '', chave)
    if chave.startswith('+'):
        return '+' + digitos
    if len(digitos) in (11, 14) and not chave.startswith('('):
        return digitos            # CPF (11) ou CNPJ (14) — telefone celular com DDD também tem 11: use (DD) ou +55
    if len(digitos) in (10, 11):
        return '+55' + digitos
    return chave


def payload(chave, nome, cidade, valor, txid='***'):
    conta = _campo('00', 'br.gov.bcb.pix') + _campo('01', chave)
    corpo = (_campo('00', '01')
             + _campo('26', conta)
             + _campo('52', '0000')
             + _campo('53', '986')
             + (_campo('54', f'{valor:.2f}') if valor else '')
             + _campo('58', 'BR')
             + _campo('59', _limpo(nome, 25) or 'RECEBEDOR')
             + _campo('60', _limpo(cidade, 15) or 'BRASIL')
             + _campo('62', _campo('05', re.sub(r'[^A-Za-z0-9]', '', txid)[:25] or '***'))
             + '6304')
    return corpo + _crc16(corpo)


def qr_svg(texto):
    import segno
    return segno.make(texto, error='m').svg_inline(scale=5, border=2, dark='#2b1a10', omitsize=True)   # viewBox: escala com o CSS
