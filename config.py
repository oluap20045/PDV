import os


class Config:
    # Em produção vem do .env do servidor; o default só serve pra rodar local.
    SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-inseguro-troque-em-producao')
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        'DATABASE_URL', 'mysql+mysqlconnector://user:password@db/pdv_db'
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    # Evita "MySQL server has gone away" depois de horas parado
    SQLALCHEMY_ENGINE_OPTIONS = {'pool_pre_ping': True, 'pool_recycle': 280}
