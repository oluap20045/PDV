# Local: app/__init__.py

import mimetypes

from flask import Flask
from config import Config
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate

mimetypes.add_type('application/wasm', '.wasm')   # leitor de código de barras (zxing)

db = SQLAlchemy()
migrate = Migrate()

def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    db.init_app(app)
    migrate.init_app(app, db)

    from app.auth import bp as auth_blueprint, exigir_login, login_manager
    login_manager.init_app(app)
    app.register_blueprint(auth_blueprint)
    app.before_request(exigir_login)   # todas as telas exigem login, menos login/cadastro

    # ALTERAÇÃO INÍCIO - Linhas 18 a 21
    # Importa o Blueprint do nosso arquivo de rotas
    from app.routes import bp as main_blueprint
    # Registra o Blueprint na aplicação
    app.register_blueprint(main_blueprint)
    from app.pedidos import bp as pedidos_blueprint
    app.register_blueprint(pedidos_blueprint)
    from app.baixas import bp as baixas_blueprint
    app.register_blueprint(baixas_blueprint)
    from app.combos import bp as combos_blueprint
    app.register_blueprint(combos_blueprint)
    from app.loja import bp as loja_blueprint, bp_admin as loja_admin_blueprint, pedidos_loja_novos
    app.register_blueprint(loja_blueprint)        # público (sem login): ver LOJA_PUBLICA em auth.py
    app.register_blueprint(loja_admin_blueprint)

    @app.context_processor
    def _selo_loja():
        from flask_login import current_user
        if not current_user.is_authenticated:
            return {}
        return {'pedidos_loja_abertos': pedidos_loja_novos()}

    # A importação de 'models' pode continuar aqui
    from app import models
    # ALTERAÇÃO FIM

    return app
