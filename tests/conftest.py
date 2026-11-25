"""Fixtures partilhadas dos testes."""

import os

import pytest


@pytest.fixture()
def app(tmp_path):
    """App Flask de teste com SQLite temporário e CSRF desativado."""
    os.environ["DATABASE_URL"] = f"sqlite:///{tmp_path}/test.db"
    os.environ.setdefault("FLASK_SECRET_KEY", "test-secret-key")

    from src import create_app, db

    application = create_app()
    application.config["WTF_CSRF_ENABLED"] = False
    application.config["TESTING"] = True

    with application.app_context():
        db.drop_all()
        db.create_all()
        yield application
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture(autouse=True)
def sem_whatsapp_real(monkeypatch):
    """Bloqueia qualquer chamada real à Evolution API durante os testes."""
    from src.services import whatsapp

    monkeypatch.setattr(whatsapp, "enviar_texto", lambda *a, **k: True)
