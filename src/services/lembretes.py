"""Rotina matinal de lembretes (executada pelo APScheduler às 08:00)."""

import random
import time
from datetime import date

from src import db
from src.models import Agendamentos
from src.services import whatsapp
from src.constants import STATUS_ATIVO, STATUS_EM_PROPOSTA, STATUS_RECUSADO_CICLO


def lembretes_matinais() -> None:
    """Notifica os clientes do dia e repõe o estado da base de dados para o novo dia."""
    hoje_str = date.today().isoformat()
    print(f"[LEMBRETES] A iniciar varredura para o dia: {hoje_str}")

    try:
        _repor_estado_diario()

        agendamentos_hoje = Agendamentos.query.filter_by(
            data=hoje_str, status=STATUS_ATIVO
        ).all()

        if not agendamentos_hoje:
            print("[LEMBRETES] Nenhum agendamento ativo encontrado para hoje.")
            return

        total = len(agendamentos_hoje)
        print(f"[LEMBRETES] Encontrados {total} lembretes para enviar.")

        for indice, agendamento in enumerate(agendamentos_hoje, start=1):
            _enviar_lembrete(agendamento, indice, total)
            if indice < total:
                time.sleep(random.randint(2, 10))

    except Exception as erro:
        print(f"[LEMBRETES] Erro geral ao processar base de dados: {erro}")


def _repor_estado_diario() -> None:
    """Liberta trancas do Caça-Vagas de ciclos anteriores."""
    print("[LEMBRETES] RECONSTRUÇÃO: A limpar trancas antigas do Caça-Vagas...")
    Agendamentos.query.filter(
        Agendamentos.status.in_([STATUS_RECUSADO_CICLO, STATUS_EM_PROPOSTA])
    ).update({Agendamentos.status: STATUS_ATIVO}, synchronize_session=False)
    db.session.commit()
    print("[LEMBRETES] ✨ Manutenção concluída. Base de dados pronta para o novo dia!")


def _enviar_lembrete(agendamento: Agendamentos, indice: int, total: int) -> None:
    cliente_nome = agendamento.nome or "Cliente"

    if not agendamento.telemovel:
        print(f"[LEMBRETES] ⚠️ [{indice}/{total}] Ignorado: {cliente_nome} não tem telemóvel registado.")
        return

    numero = whatsapp.normalizar_telemovel(agendamento.telemovel)
    texto = whatsapp.mensagem_lembrete(agendamento)

    try:
        if whatsapp.enviar_texto(numero, texto, delay_ms=1500, timeout=10):
            print(f"[LEMBRETES] ✅ [{indice}/{total}] Enviado com sucesso para {agendamento.nome}.")
        else:
            print(f"[LEMBRETES] ⚠️ Erro no envio para {agendamento.nome}.")
    except Exception as erro:
        print(f"[LEMBRETES] ❌ [{indice}/{total}] Falha ao enviar para {cliente_nome}: {erro}")
