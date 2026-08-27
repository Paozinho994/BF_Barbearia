import os
from flask import Flask
from dotenv import load_dotenv
from flask_sqlalchemy import SQLAlchemy
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

# Carrega as variáveis de ambiente do ficheiro .env global
load_dotenv()
db = SQLAlchemy()

scheduler = BackgroundScheduler(timezone="Europe/Lisbon")

def executar_lembrete_com_contexto(app_instancia):
    """Garante que a query corre com o contexto correto da aplicação passada por parâmetro."""
    with app_instancia.app_context():
        from src.rotas.admin import lembretes_matinais
        lembretes_matinais()

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


    scheduler.remove_all_jobs()

        # Agenda a tarefa para correr rigorosamente às 08:00h da manhã todos os dias
    scheduler.add_job(
        executar_lembrete_com_contexto,
        trigger=CronTrigger(hour=8, minute=0, second=0),
        id="lembretes_diarios_08am",
        args=[app],  # Passa a app como argumento
        replace_existing=True
    )

    scheduler.start()
    app.config['SCHEDULER_INICIADO'] = True
    print("\n[SISTEMA] 🚀 Motor APScheduler acoplado e trancado com sucesso!")

    return app
