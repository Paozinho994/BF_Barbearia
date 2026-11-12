import os
from flask import Flask
from dotenv import load_dotenv
from flask_sqlalchemy import SQLAlchemy
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from flask_wtf.csrf import CSRFProtect

# Carrega as variáveis de ambiente do ficheiro .env global
load_dotenv()
db = SQLAlchemy()
csrf = CSRFProtect()
scheduler = BackgroundScheduler(timezone="Europe/Lisbon")


def _executar_lembretes(app_instancia):
    """Corre os lembretes matinais dentro do contexto da app."""
    with app_instancia.app_context():
        from src.services.lembretes import lembretes_matinais
        lembretes_matinais()


def _iniciar_scheduler(app: Flask) -> None:
    """Agenda a rotina diária das 08:00 e arranca o scheduler."""
    scheduler.remove_all_jobs()
    scheduler.add_job(
        _executar_lembretes,
        trigger=CronTrigger(hour=8, minute=0, second=0),
        id="lembretes_diarios_08am",
        args=[app],
        replace_existing=True,
    )
    scheduler.start()
    app.config["SCHEDULER_INICIADO"] = True


def create_app() -> Flask:
    """Factory function para inicializar e configurar a aplicação Flask."""
    app = Flask(__name__, template_folder="templates", static_folder="static")

    uri = os.getenv("DATABASE_URL", "sqlite:///bf_barbearia_fallback.db")
    if uri and uri.startswith("postgres://"):
        uri = uri.replace("postgres://", "postgresql://", 1)

    app.config.update(
        SQLALCHEMY_DATABASE_URI=uri,
        SECRET_KEY=os.getenv("FLASK_SECRET_KEY", "chave-secreta-provisoria-para-dev"),
        DEBUG=os.getenv("FLASK_DEBUG", "0") == "1",
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SECURE=True,
        SESSION_COOKIE_SAMESITE="Lax",
    )

    db.init_app(app)
    csrf.init_app(app)

    from src.rotas.cliente import cliente_bp
    from src.rotas.admin import admin_bp

    app.register_blueprint(cliente_bp)
    app.register_blueprint(admin_bp, url_prefix="/admin")
    csrf.exempt("cliente.confirmar_antecipacao")

    with app.app_context():
        db.create_all()

    _iniciar_scheduler(app)
    return app
