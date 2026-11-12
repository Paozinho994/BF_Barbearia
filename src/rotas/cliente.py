"""Rotas públicas do cliente (site de marcação)."""

import hmac
import os
from datetime import datetime

from flask import Blueprint, jsonify, render_template, request, abort

from src.constants import HORARIOS
from src.services import agendamentos

# Inicializa o Blueprint do cliente público
cliente_bp = Blueprint("cliente", __name__)


@cliente_bp.route("/")
def index() -> str:
    """Interface pública de agendamento."""
    return render_template(
        "cliente/agendamentos.html",
        horarios=HORARIOS,
        data_atual_sistema=datetime.now().strftime("%Y-%m-%d"),
    )


@cliente_bp.route("/agendar", methods=["POST"])
def agendar():
    """Recebe o formulário de marcação, valida e grava o agendamento."""
    dados = {
        "servico": request.form.get("servico", ""),
        "data": request.form.get("data", ""),
        "barbeiro": request.form.get("barbeiro", ""),
        "hora": request.form.get("hora", ""),
        "nome": request.form.get("nome", "").strip(),
        "telemovel": request.form.get("telemovel", "").strip(),
        "canal": request.form.get("canal", "whatsapp"),
    }

    agendamento, erro = agendamentos.criar_agendamento_online(dados)
    if erro:
        corpo, status = erro
        return corpo, status

    return render_template(
        "cliente/sucesso.html",
        nome_cliente=agendamento.nome,
        servico_escolhido=agendamento.servico,
        data_escolhida=agendamento.data,
        hora_escolhida=agendamento.hora,
        canal_notificacao=agendamento.canal,
    )


@cliente_bp.route("/verificar-disponibilidade")
def verificar_disponibilidade():
    """API que devolve os horários livres para uma data/barbeiro."""
    data = request.args.get("data", "")
    barbeiro = request.args.get("barbeiro", "")
    return jsonify(agendamentos.horarios_livres(data, barbeiro))


@cliente_bp.route("/webhook/confirmar-antecipacao", methods=["POST"])
def confirmar_antecipacao():
    """Webhook que recebe a resposta SIM/NÃO do cliente via WhatsApp."""
    token_recebido = request.args.get("token", "")
    token_oficial = os.getenv("WEBHOOK_TOKEN", "")
    if not token_oficial or not hmac.compare_digest(token_recebido, token_oficial):
        print("❌ [WEBHOOK] Token inválido ou não autorizado!")
        return jsonify({"status": "erro", "motivo": "Não autorizado"}), 403

    dados_webhook = request.get_json(silent=True) or {}
    payload, status = agendamentos.processar_resposta_canca_vagas(dados_webhook)
    return jsonify(payload), status


@cliente_bp.route("/cancelar_vaga/<string:token>", methods=["GET", "POST"])
def cancelamento_publico(token: str):
    """Página pública de cancelamento que aciona o Caça-Vagas."""
    agendamento = agendamentos.buscar_por_token_cancelamento(token)
    if not agendamento:
        abort(404)

    if request.method == "POST":
        nome_cliente = agendamento.nome
        data_corte = agendamento.data
        hora_corte = agendamento.hora
        agendamentos.executar_algoritmo_caca_vagas(agendamento.id)
        return render_template(
            "cliente/cancelado_post.html",
            nome_cliente=nome_cliente,
            data_corte=data_corte,
            hora_corte=hora_corte,
        )

    return render_template("cliente/cancelar_get.html", agendamento=agendamento)