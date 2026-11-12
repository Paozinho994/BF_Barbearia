"""Rotas do painel de administração."""

import os
from datetime import datetime

from flask import Blueprint, render_template, request, redirect, url_for, session, abort
from werkzeug.security import generate_password_hash, check_password_hash

from src.constants import HORARIOS
from src.services import agendamentos

admin_bp = Blueprint("admin", __name__)


# 🔒 SENTINELA DE SEGURANÇA: protege todas as rotas do Blueprint /admin
@admin_bp.before_request
def verificar_autenticacao():
    if request.endpoint == "admin.login":
        return
    if not session.get("admin_logado"):
        return redirect(url_for("admin.login"))


# 🔑 LOGIN & PROCESSAMENTO
@admin_bp.route("/login", methods=["GET", "POST"])
def login():
    erro = None
    if request.method == "POST":
        utilizador = request.form.get("utilizador", "").strip()
        senha = request.form.get("senha", "")

        admin = os.getenv("ADMIN_USER")
        admin_password = os.getenv("SENHA")

        if not admin or not admin_password:
            print("🚨 [SEGURANÇA] ADMIN_USER ou SENHA não configurados!")
            abort(500, "Erro interno de configuração de segurança.")

        if utilizador == admin and check_password_hash(generate_password_hash(admin_password), senha):
            session["admin_logado"] = True
            return redirect(url_for("admin.dashboard"))
        erro = "Utilizador ou Password incorretos!"

    return render_template("admin/login.html", erro=erro)


# 🚪 LOGOUT
@admin_bp.route("/logout")
def logout():
    session.pop("admin_logado", None)
    return redirect(url_for("admin.login"))


@admin_bp.route("/")
def dashboard() -> str:
    """Painel de administração principal."""
    contexto = agendamentos.montar_contexto_dashboard(
        request.args.get("data", ""),
        request.args.get("barbeiro", ""),
    )
    contexto["horarios"] = HORARIOS
    return render_template("admin/dashboard.html", **contexto)


@admin_bp.route("/marcar", methods=["POST"])
def criar_marcacao_manual():
    """Recebe e processa os dados do formulário de marcação manual."""
    dados = {
        "nome": request.form.get("nome", "").strip(),
        "telemovel": request.form.get("telemovel", "").strip(),
        "hora": request.form.get("hora", ""),
        "data": request.form.get("data") or datetime.now().strftime("%Y-%m-%d"),
        "barbeiro": request.form.get("barbeiro", "barbeiro_1"),
        "canal": request.form.get("canal", "nenhum"),
    }

    _, erro = agendamentos.criar_marcacao_manual(dados)
    if erro:
        corpo, status = erro
        return corpo, status

    return redirect(url_for("admin.dashboard"))


@admin_bp.route("/cancelar/<int:id_agendamento>", methods=["POST"])
def cancelar_ou_noshow(id_agendamento: int):
    """Aciona o Motor do Caça-Vagas para um agendamento."""
    if not agendamentos.executar_algoritmo_caca_vagas(id_agendamento):
        return "Erro: Agendamento não encontrado ou já cancelado.", 400
    return redirect(url_for("admin.dashboard"))


@admin_bp.route("/relatorio")
def ver_relatorio():
    """Relatório de faturação recuperada pelo Caça-Vagas."""
    return render_template("admin/relatorio.html", **agendamentos.montar_relatorio())