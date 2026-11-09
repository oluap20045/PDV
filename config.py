import os
from datetime import timedelta


class Config:
    # Em produção vem do .env do servidor; o default só serve pra rodar local.
    SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-inseguro-troque-em-producao')
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        'DATABASE_URL', 'mysql+mysqlconnector://user:password@db/pdv_db'
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    # Evita "MySQL server has gone away" depois de horas parado
    SQLALCHEMY_ENGINE_OPTIONS = {'pool_pre_ping': True, 'pool_recycle': 280}

    # Sessão/login: cookie inacessível ao JavaScript e não enviado em POST vindo de outro site
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    REMEMBER_COOKIE_HTTPONLY = True
    REMEMBER_COOKIE_SAMESITE = 'Lax'
    REMEMBER_COOKIE_DURATION = timedelta(days=30)   # "manter conectado" no celular do caixa
    # atrás do Caddy é sempre HTTPS; em dev (http) defina COOKIE_SEGURO=0
    SESSION_COOKIE_SECURE = REMEMBER_COOKIE_SECURE = os.environ.get('COOKIE_SEGURO', '1') == '1'
