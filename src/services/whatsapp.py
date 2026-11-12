"""Integração com a Evolution API (WhatsApp) e utilitários de contacto.

Centraliza tudo o que diz respeito ao envio de mensagens e à
normalização de números de telemóvel, evitando duplicação entre
rotas, agendamentos e o motor Caça-Vagas.
"""

import os
import random
import re

import requests

from src.constants import BARBEIROS, TIMEOUT_CACA_VAGAS_MINUTOS

INSTANCIA_WHATSAPP = "BF-Barbearia"
SUFIXO_ENDPOINT = f"/message/sendText/{INSTANCIA_WHATSAPP}"


def _config_evolution() -> tuple[str, dict]:
    """Devolve (url, headers) da Evolution API a partir das variáveis de ambiente."""
    api_base = os.getenv("EVOLUTION_API_URL", "https://obtuse-pasty-traitor.ngrok-free.dev")
    api_base_limpa = api_base.replace(SUFIXO_ENDPOINT, "").rstrip("/")
    url = f"{api_base_limpa}{SUFIXO_ENDPOINT}"
    api_key = os.getenv("EVOLUTION_API_KEY", os.getenv("FLASK_SECRET_KEY", ""))
    headers = {"apikey": api_key, "Content-Type": "application/json"}
    return url, headers


def enviar_texto(numero: str, texto: str, delay_ms: int = 1200,
                presence: str = "composing", timeout: int = 12) -> bool:
    """Envia uma mensagem de texto via Evolution API. Devolve True em caso de sucesso."""
    url, headers = _config_evolution()
    payload = {
        "number": numero,
        "options": {"delay": delay_ms, "presence": presence},
        "text": texto,
    }
    try:
        resposta = requests.post(url, json=payload, headers=headers, timeout=timeout)
        if resposta.status_code in (200, 201):
            return True
        print(f"⚠️ [WHATSAPP] Envio recusado. Status: {resposta.status_code} | {resposta.text}")
    except requests.exceptions.RequestException as erro:
        print(f"❌ [WHATSAPP] Falha de rede ao contactar a Evolution API: {erro}")
    return False


def normalizar_telemovel(telemovel: str) -> str:
    """Remove tudo o que não é dígito e garante o prefixo 351 para números nacionais."""
    digitos = re.sub(r"\D", "", telemovel or "")
    if len(digitos) == 9:
        return f"351{digitos}"
    return digitos


def telemovel_valido(telemovel: str, estrito: bool = False) -> bool:
    """Valida um telemóvel português. `estrito` aplica a regra de prefixo do site público."""
    digitos = re.sub(r"\D", "", telemovel or "")
    if estrito:
        return bool(re.match(r"^9[12367]\d{7}$", digitos))
    return bool(re.match(r"^9\d{8}$", digitos))


def jid_whatsapp(telemovel: str) -> str:
    """Converte um telemóvel no formato JID esperado pela Evolution API."""
    return f"{normalizar_telemovel(telemovel)}@s.whatsapp.net"


def nome_barbeiro(barbeiro: str) -> str:
    """Nome público do profissional a partir do identificador interno."""
    return BARBEIROS.get(barbeiro, "Equipa BF")


def formatar_servico(servico: str) -> str:
    """Formatação estética do nome do serviço para mensagens."""
    return (servico or "Serviço").replace("+", " + ").upper().strip()


def url_cancelamento(token: str) -> str:
    """URL pública do link de cancelamento/antecipação."""
    base = os.getenv("URL_PUBLICO_SaaS", "http://bf-barbearia.onrender.com")
    return f"{base}/cancelar_vaga/{token}"


# ---------------------------------------------------------------------------
# Construtores de mensagens
# ---------------------------------------------------------------------------

def mensagem_confirmacao(agendamento: dict) -> str:
    """Mensagem de confirmação de marcação enviada ao cliente."""
    link = url_cancelamento(agendamento.get("token_cancelamento", ""))
    return (
        f"Olá {agendamento.get('nome', '')}! 👋\n\n"
        f"O teu corte de **{formatar_servico(agendamento.get('servico', ''))}** está confirmado na **BF Barbearia**! 💈\n"
        f"📅 Data: {agendamento.get('data', '')}\n"
        f"⏰ Hora: {agendamento.get('hora', '')}\n"
        f"✂️ Profissional: {nome_barbeiro(agendamento.get('barbeiro', ''))}\n\n"
        f"Se precisares de alterar ou cancelar, clica aqui até 2h antes:\n{link}\n\n"
        f"Até já! 🔥"
    )


def mensagem_convite_caca_vagas(cliente, vaga_cancelada: dict) -> str:
    """Convite de antecipação enviado ao próximo cliente da fila."""
    return (
        f"Olá {cliente.nome}! 👋 Notícia fantástica da **BF Barbearia**! 💈\n\n"
        f"Uma vaga de última hora acabou de abrir para **dia {vaga_cancelada['data']} às {vaga_cancelada['hora']}** "
        f"com o profissional {nome_barbeiro(vaga_cancelada['barbeiro'])}.\n\n"
        f"Como tens corte marcado para o dia {cliente.data} às {cliente.hora}, "
        f"gostarias de antecipar o teu atendimento?\n\n"
        f"⏳ *Nota:* Tens **{TIMEOUT_CACA_VAGAS_MINUTOS} minutos** para responder antes que a vaga passe para o próximo cliente.\n\n"
        f"🔥 Responde **SIM** para aceitar a troca automática ou **NÃO** para passar a oportunidade."
    )


def mensagem_feedback_recusa(cliente) -> str:
    """Mensagem de cortesia quando o cliente recusa a vaga."""
    return (
        f"Obrigado pela tua resposta, {cliente.nome}! 👍\n\n"
        f"Fica descansado, o teu corte mantém-se rigorosamente agendado para "
        f"**dia {cliente.data} às {cliente.hora}**. Vemo-nos brevemente! 💈"
    )


def mensagem_timeout_caca_vagas(cliente) -> str:
    """Aviso de que o tempo de resposta do Caça-Vagas expirou."""
    return (
        f"Olá, {cliente.nome}! ⏳\n\n"
        f"O limite de **30 minutos** para uma resposta terminou."
        f"Mas não te preocupes. O teu corte continua **100% confirmado para o dia {cliente.data} às {cliente.hora}**. Até breve! 💈"
    )


def mensagem_troca_concluida(agendamento: dict) -> str:
    """Comprovativo de que o horário foi alterado com sucesso."""
    return (
        f"Concluído com sucesso, {agendamento['nome']}! 🔥\n\n"
        f"O teu horário foi alterado automaticamente no sistema da **BF Barbearia**. 🚀\n"
        f"Esperamos por ti no novo dia **{agendamento['data']} às {agendamento['hora']}** "
        f"com o barbeiro {nome_barbeiro(agendamento['barbeiro'])}.\n\n"
        f"O teu horário antigo foi libertado. Obrigado por nos ajudar a manter a agenda cheia! 💈"
    )


def mensagem_lembrete(agendamento) -> str:
    """Lembrete matinal com variação aleatória de saudação."""
    import random

    saudacoes = ["Olá,", "Viva,", "Boas,", "Como estás,"]
    lembretes = [
        "Passamos para lembrar que o teu corte está agendado para",
        "Vimos recordar-te que o teu corte está agendado para",
        "Informamos que o teu corte está agendado para",
    ]
    despedidas = ["Até já! ✂️", "Contamos contigo! 💈", "Abraço de toda a equipe!"]
    return (
        f"{random.choice(saudacoes)} {agendamento.nome}! "
        f"{random.choice(lembretes)} hoje, às {agendamento.hora}. "
        f"{random.choice(despedidas)}"
    )


# ---------------------------------------------------------------------------
# Disparadores de alto nível
# ---------------------------------------------------------------------------

def disparar_notificacao_inteligente(agendamento: dict, origem: str = "ONLINE") -> None:
    """Motor único de notificações (usado por clientes e admin)."""
    canal = agendamento.get("canal", "whatsapp")
    if canal in ("nenhum", "sms"):
        print(f"➔ [{origem}] Nenhuma notificação digital agendada por opção do cliente/sistema.")
        return

    print(f"\n➔[{origem}] A processar envio via {canal.upper()}")

    if canal == "whatsapp":
        texto = mensagem_confirmacao(agendamento)
        print("-" * 42)
        print(texto)
        print("-" * 42)
        numero = normalizar_telemovel(agendamento.get("telemovel", ""))
        if enviar_texto(numero, texto, delay_ms=1200):
            print(f"🚀 [WHATSAPP REAL] Mensagem entregue com sucesso para "
                  f"{agendamento.get('nome')} ({numero})")

    print(f"\n[SUCESSO] Horário {agendamento.get('hora')} bloqueado para "
          f"{agendamento.get('barbeiro')} no dia {agendamento.get('data')}.\n")

    print(f"\n========[REGISTO DE SISTEMA - {origem}]========")
    print(f"Cliente: {agendamento.get('nome')} ({normalizar_telemovel(agendamento.get('telemovel', ''))})")
    print(f"Serviço: {formatar_servico(agendamento.get('servico', ''))}")
    print(f"Profissional: {str(agendamento.get('barbeiro', '')).replace('_', '').title()}")
    print(f"Data/Hora: {agendamento.get('data')} às {agendamento.get('hora')}")
    print(f"Canal de Alerta: Enviar lembrete automático via {canal.upper()}")
    print("=" * 42)


def enviar_alerta_troca_concluida(agendamento: dict) -> None:
    """Envia o comprovativo de troca de horário concluída pelo motor Caça-Vagas."""
    texto = mensagem_troca_concluida(agendamento)
    numero = jid_whatsapp(agendamento["telemovel"])
    print(f"\n➔ [MOTOR] A disparar WhatsApp real de sucesso para {agendamento['nome']} ({numero})...")
    if enviar_texto(numero, texto, delay_ms=1200):
        print("✅ [WHATSAPP] Mensagem de troca concluída entregue com sucesso!")
