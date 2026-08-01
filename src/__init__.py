import os
from flask import Flask
from dotenv import load_dotenv
from flask_sqlalchemy import SQLAlchemy

# Carrega as variáveis de ambiente do ficheiro .env global
load_dotenv()
db = SQLAlchemy()


def create_app() -> Flask:
    """Factory function para inicializar e configurar a aplicação Flask."""

    # Definimos explicitamente onde estão os templates para evitar erros de caminhos
    app = Flask(
        __name__,
        template_folder='templates',
        static_folder='static'
    )

    uri = os.getenv("DATABASE_URL", "sqlite:///bf_barbearia_fallback.db")
    if uri and uri.startswith("postgres://"):
        uri = uri.replace("postgres://", "postgresql://", 1)

    app.config["SQLALCHEMY_DATABASE_URI"] = uri

    # Configurações modernas de segurança e ambiente
    app.config.update(
        SECRET_KEY=os.getenv("FLASK_SECRET_KEY", "chave-secreta-provisoria-para-dev"),
        ENV=os.getenv("FLASK_ENV", "production")
    )

    db.init_app(app)

    # Registo dos Blueprints (Módulos de Rotas Isolados)
    from src.rotas.cliente import cliente_bp
    from src.rotas.admin import admin_bp

    # A rota do cliente será a raiz (/) e a do admin terá o prefixo (/admin)
    app.register_blueprint(cliente_bp)
    app.register_blueprint(admin_bp, url_prefix='/admin')

    return app
