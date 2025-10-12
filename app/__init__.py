# Local: app/__init__.py

from flask import Flask
from config import Config
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate

db = SQLAlchemy()
migrate = Migrate()

def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    db.init_app(app)
    migrate.init_app(app, db)

    # ALTERAÇÃO INÍCIO - Linhas 18 a 21
    # Importa o Blueprint do nosso arquivo de rotas
    from app.routes import bp as main_blueprint
    # Registra o Blueprint na aplicação
    app.register_blueprint(main_blueprint)

    # A importação de 'models' pode continuar aqui
    from app import models
    # ALTERAÇÃO FIM

    return app
