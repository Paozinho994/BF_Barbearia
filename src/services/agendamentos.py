"""Regras de negócio de agendamentos da BF Barbearia.

Contém toda a lógica que não é HTTP: validação, atribuição de barbeiro,
disponibilidade, cancelamento, o motor Caça-Vagas e o processamento
do webhook de respostas SIM/NÃO.
"""

import random
import re
from datetime import date, datetime, timedelta

import pytz
from flask import current_app

from src import db, scheduler
from src.constants import (
    BARBEIROS_INDIVIDUAIS,
    CANAL_RECUSADO,
    DIAS_FECHADOS,
    FORMATO_DATA,
    FORMATO_DATA_HORA,
    FORMATO_HORA,
    HORARIOS,
    JANELA_SILENCIO,
    MARGEM_ANTECEDENCIA_MINUTOS,
    MESES_PT,
    PRECOS_SERVICOS,
    PRECO_PADRAO,
    STATUS_ATIVO,
    STATUS_CANCELADO,
    STATUS_EM_PROPOSTA,
    STATUS_RECUSADO_CICLO,
    TIMEOUT_CACA_VAGAS_MINUTOS,
)
from src.models import Agendamentos, HistoricoCacaVagas
from src.services import whatsapp

SERVICO_MANUAL = "Marcação Manual (Telefone)"


# ---------------------------------------------------------------------------
# Marcação online (site público)
# ---------------------------------------------------------------------------

def criar_agendamento_online(dados: dict):
    """Valida e grava um agendamento feito no site público.

    Retorna (agendamento, None) em sucesso ou (None, (html_erro, 400)).
    """
    agora = datetime.now()
    hoje_str = agora.strftime(FORMATO_DATA)
    hora_agora_str = agora.strftime(FORMATO_HORA)

    data = dados["data"]
    hora = dados["hora"]
    barbeiro = dados["barbeiro"]

    if data < hoje_str or (data == hoje_str and hora <= hora_agora_str):
        return None, ("<h1>Erro: Não é permitido efetuar agendamentos para datas ou horários passados!</h1>", 400)

    if not whatsapp.telemovel_valido(dados["telemovel"], estrito=True):
        return None, ("<h1>Erro: O número de telemóvel introduzido é inválido. "
                      "Certifique-se de que tem 9 dígitos e começa por 91, 92, 93, 96 ou 97!</h1>", 400)

    if not all([dados["servico"], data, barbeiro, hora, dados["nome"], dados["telemovel"]]):
        return None, ("Erro: Todos os campos obrigatórios devem ser preenchidos.", 400)

    barbeiro_final = _escolher_barbeiro(data, hora, barbeiro)
    if barbeiro_final is None:
        return None, ("<h1>Erro: Este horário acabou de ser preenchido. Por favor, escolha outra hora!</h1>", 400)

    if barbeiro != "qualquer" and _horario_ocupado(data, hora, barbeiro_final):
        return None, ("<h1>Erro: Este horário acabou de ser preenchido por outro cliente há poucos segundos!</h1>", 400)

    agendamento = Agendamentos(
        data=data,
        barbeiro=barbeiro_final,
        hora=hora,
        nome=dados["nome"],
        telemovel=dados["telemovel"],
        servico=dados["servico"],
        canal=dados["canal"],
        status=STATUS_ATIVO,
    )
    db.session.add(agendamento)
    db.session.commit()

    whatsapp.disparar_notificacao_inteligente(_dados_notificacao(agendamento), origem="ONLINE")
    return agendamento, None


def _escolher_barbeiro(data: str, hora: str, preferencia: str) -> str | None:
    """Resolve o barbeiro final. Devolve None se a hora estiver lotada (opção 'qualquer')."""
    if preferencia != "qualquer":
        return preferencia

    ocupados = {
        barbeiro: _horario_ocupado(data, hora, barbeiro)
        for barbeiro in BARBEIROS_INDIVIDUAIS
    }
    if all(ocupados.values()):
        return None
    if ocupados["barbeiro_1"]:
        return "barbeiro_2"
    if ocupados["barbeiro_2"]:
        return "barbeiro_1"
    return random.choice(list(BARBEIROS_INDIVIDUAIS))


def _horario_ocupado(data: str, hora: str, barbeiro: str) -> bool:
    return Agendamentos.query.filter_by(
        data=data, hora=hora, barbeiro=barbeiro, status=STATUS_ATIVO
    ).first() is not None


def _dados_notificacao(agendamento: Agendamentos) -> dict:
    return {
        "id": agendamento.id,
        "data": agendamento.data,
        "barbeiro": agendamento.barbeiro,
        "hora": agendamento.hora,
        "nome": agendamento.nome,
        "telemovel": agendamento.telemovel,
        "servico": agendamento.servico,
        "canal": agendamento.canal,
        "token_cancelamento": agendamento.token_cancelamento,
    }


# ---------------------------------------------------------------------------
# Disponibilidade
# ---------------------------------------------------------------------------

def horarios_livres(data: str, barbeiro: str) -> list[str]:
    """Horários livres para uma data/barbeiro, já com bloqueios de passado e dias fechados."""
    if not data or not barbeiro:
        return list(HORARIOS)

    agora = datetime.now()
    if barbeiro != "qualquer":
        ocupadas = {m.hora for m in Agendamentos.query.filter_by(
            data=data, barbeiro=barbeiro, status=STATUS_ATIVO
        ).all()}
        livres = [h for h in HORARIOS if h not in ocupadas]
    else:
        ocupadas_b1 = {m.hora for m in Agendamentos.query.filter_by(
            data=data, barbeiro="barbeiro_1", status=STATUS_ATIVO
        ).all()}
        ocupadas_b2 = {m.hora for m in Agendamentos.query.filter_by(
            data=data, barbeiro="barbeiro_2", status=STATUS_ATIVO
        ).all()}
        hora_cheia = ocupadas_b1 & ocupadas_b2
        livres = [h for h in HORARIOS if h not in hora_cheia]

    livres = _aplicar_restricoes_temporais(livres, data, agora)
    return livres


def _aplicar_restricoes_temporais(livres: list[str], data: str, agora: datetime) -> list[str]:
    """Remove horários passados e dias em que a barbearia está fechada."""
    hoje_str = agora.strftime(FORMATO_DATA)
    hora_atual_str = agora.strftime(FORMATO_HORA)

    if data < hoje_str:
        return []
    if data == hoje_str:
        livres = [h for h in livres if h > hora_atual_str]

    try:
        if datetime.strptime(data, FORMATO_DATA).weekday() in DIAS_FECHADOS:
            return []
    except ValueError:
        pass
    return livres


# ---------------------------------------------------------------------------
# Cancelamento público
# ---------------------------------------------------------------------------

def buscar_por_token_cancelamento(token: str) -> Agendamentos | None:
    return Agendamentos.query.filter_by(
        token_cancelamento=token, status=STATUS_ATIVO
    ).first()


# ---------------------------------------------------------------------------
# Marcação manual (painel admin)
# ---------------------------------------------------------------------------

def criar_marcacao_manual(dados: dict):
    """Cria uma marcação registada pelo barbeiro no balcão/painel.

    Retorna (agendamento, None) ou (None, (html_erro, 400)).
    """
    if not all([dados["nome"], dados["telemovel"], dados["hora"]]):
        return None, ("Erro: Todos os campos são obrigatórios.", 400)

    telemovel_limpo = re.sub(r"\D", "", dados["telemovel"])
    if not re.match(r"^9\d{8}$", telemovel_limpo):
        return None, (
            "<h1>Erro: O número de telemóvel introduzido no painel é inválido!</h1>"
            "<p>Certifique-se de que inseriu exatamente 9 dígitos e que o número começa por 9 (ex: 912345678).</p>"
            "<br><a href='javascript:history.back()'>← Voltar Atrás</a>",
            400,
        )

    if _horario_ocupado(dados["data"], dados["hora"], dados["barbeiro"]):
        return None, (f"<h1>Erro: O horário {dados['hora']} para esta data já foi preenchido por outro cliente!</h1>", 400)

    agendamento = Agendamentos(
        data=dados["data"],
        barbeiro=dados["barbeiro"],
        hora=dados["hora"],
        nome=dados["nome"],
        telemovel=telemovel_limpo,
        servico=SERVICO_MANUAL,
        canal=dados["canal"],
        status=STATUS_ATIVO,
    )
    db.session.add(agendamento)
    db.session.commit()

    whatsapp.disparar_notificacao_inteligente(_dados_notificacao(agendamento), origem="MANUAL/BALCÃO")
    return agendamento, None


# ---------------------------------------------------------------------------
# Motor Caça-Vagas
# ---------------------------------------------------------------------------

def executar_algoritmo_caca_vagas(id_agendamento: int) -> bool:
    """Motor centralizado do Caça-Vagas. Devolve False se o agendamento não existir."""
    agendamento = db.session.get(Agendamentos, id_agendamento)
    if not agendamento:
        print(f"⚠️ [MOTOR CENTRAL] Agendamento {id_agendamento} não encontrado. A verificar fila de espera...")
        Agendamentos.query.filter_by(status=STATUS_RECUSADO_CICLO).update(
            {Agendamentos.status: STATUS_ATIVO}
        )
        db.session.commit()
        return False

    if agendamento.status != STATUS_ATIVO:
        print(f"⚠️ [MOTOR CENTRAL] Agendamento {id_agendamento} já não está ativo. A verificar fila de espera...")

    data_cancelada = agendamento.data
    hora_cancelada = agendamento.hora
    barbeiro_cancelado = agendamento.barbeiro

    if _em_janela_silencio():
        _libertar_vaga(agendamento)
        print(f"[JANELA INTELIGENTE] 🔕 Silêncio Noturno. Vaga libertada, mas convites congelados.")
        return True

    if _vaga_muito_proxima(data_cancelada, hora_cancelada):
        _libertar_vaga(agendamento)
        print(f"[JANELA INTELIGENTE] ⏱️ Vaga das {hora_cancelada} está muito em cima da hora. Convites abortados.")
        return True

    _libertar_vaga(agendamento)
    _propor_proximo_cliente(id_agendamento, data_cancelada, hora_cancelada, barbeiro_cancelado)
    return True


def _em_janela_silencio() -> bool:
    hora = datetime.now().hour
    inicio, fim = JANELA_SILENCIO
    return hora >= inicio or hora < fim


def _vaga_muito_proxima(data: str, hora: str) -> bool:
    if data != datetime.now().strftime(FORMATO_DATA):
        return False
    try:
        vaga = datetime.strptime(f"{data} {hora}", FORMATO_DATA_HORA)
        return vaga - datetime.now() < timedelta(minutes=MARGEM_ANTECEDENCIA_MINUTOS)
    except ValueError:
        return False


def _libertar_vaga(agendamento: Agendamentos) -> None:
    if agendamento.status == STATUS_ATIVO:
        agendamento.status = STATUS_CANCELADO
        db.session.commit()


def _propor_proximo_cliente(id_agendamento: int, data_cancelada: str,
                            hora_cancelada: str, barbeiro_cancelado: str) -> None:
    """Escolhe o próximo cliente da fila e envia-lhe o convite de antecipação."""
    candidatos = Agendamentos.query.filter(
        Agendamentos.hora == hora_cancelada,
        Agendamentos.barbeiro == barbeiro_cancelado,
        Agendamentos.status == STATUS_ATIVO,
        Agendamentos.nome != None,  # noqa: E711 - intencional no SQLAlchemy
        Agendamentos.data > data_cancelada,
        Agendamentos.canal != CANAL_RECUSADO,
    ).order_by(Agendamentos.data).all()

    if not candidatos:
        print("💡 [MOTOR CENTRAL] Sem clientes em fila de espera para este horário. Vaga aberta no site.")
        db.session.commit()
        return

    cliente_alvo = candidatos[0]
    print(f"🚀 [MOTOR CENTRAL] Cliente prioritário detetado: {cliente_alvo.nome}")

    cliente_alvo.status = STATUS_EM_PROPOSTA
    db.session.commit()

    _enviar_convite(cliente_alvo, data_cancelada, hora_cancelada, barbeiro_cancelado)
    _agendar_timeout(cliente_alvo.id, id_agendamento)
    print(f"⏱️ [CAÇA-VAGAS] Temporizador de {TIMEOUT_CACA_VAGAS_MINUTOS} minutos ativado "
          f"para {cliente_alvo.nome} (ID: {cliente_alvo.id}).")


def _enviar_convite(cliente, data_cancelada: str, hora_cancelada: str, barbeiro_cancelado: str) -> None:
    if cliente.canal not in ("whatsapp", "nenhum"):
        return

    vaga = {"data": data_cancelada, "hora": hora_cancelada, "barbeiro": barbeiro_cancelado}
    texto = whatsapp.mensagem_convite_caca_vagas(cliente, vaga)
    numero = whatsapp.normalizar_telemovel(cliente.telemovel)

    if whatsapp.enviar_texto(numero, texto, delay_ms=3000, timeout=8):
        print(f"🚀 [CAÇA-VAGAS WHATSAPP] Convite do Caça-Vagas entregue a {cliente.nome}")


def _agendar_timeout(id_cliente: int, id_vaga_cancelada: int) -> None:
    tz = pytz.timezone("Europe/Lisbon")
    tempo_limite = datetime.now(tz) + timedelta(minutes=TIMEOUT_CACA_VAGAS_MINUTOS)
    app_real = current_app._get_current_object()

    scheduler.add_job(
        verificar_timeout_caca_vagas,
        trigger="date",
        run_date=tempo_limite,
        args=[id_cliente, id_vaga_cancelada, app_real],
        id=f"timeout_caca_vagas_{id_cliente}",
        replace_existing=True,
    )


def verificar_timeout_caca_vagas(id_cliente: int, id_vaga_cancelada: int, app_instancia) -> None:
    """Retaguarda: corre se o cliente ignorar o convite durante o tempo limite."""
    with app_instancia.app_context():
        cliente = db.session.get(Agendamentos, id_cliente)

        if not (cliente and cliente.status == STATUS_EM_PROPOSTA):
            nome = cliente.nome if cliente else id_cliente
            print(f"✅ [TIMEOUT] Verificação concluída: O cliente {nome} respondeu a tempo ou foi modificado.")
            return

        print(f"⏳ [TIMEOUT {TIMEOUT_CACA_VAGAS_MINUTOS} MIN] O cliente {cliente.nome} não respondeu. A libertar vaga...")

        # 'recusado_ciclo' faz o motor saltar este cliente apenas neste ciclo
        cliente.status = STATUS_RECUSADO_CICLO
        db.session.commit()

        whatsapp.enviar_texto(
            whatsapp.normalizar_telemovel(cliente.telemovel),
            whatsapp.mensagem_timeout_caca_vagas(cliente),
            delay_ms=1500,
            timeout=5,
        )
        print(f"⏱️ [TIMEOUT] Notificação de tempo limite enviada com sucesso para {cliente.nome}.")

        print("⏭️ [TIMEOUT] A saltar para o próximo candidato da fila...")
        executar_algoritmo_caca_vagas(id_agendamento=id_vaga_cancelada)


def cancelar_job_timeout(id_cliente: int) -> None:
    """Remove o temporizador do Caça-Vagas de um cliente, se existir."""
    try:
        scheduler.remove_job(f"timeout_caca_vagas_{id_cliente}")
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Webhook de respostas SIM/NÃO (Evolution API)
# ---------------------------------------------------------------------------

def processar_resposta_canca_vagas(dados_webhook: dict) -> tuple[dict, int]:
    """Processa a resposta do cliente ao convite de antecipação.

    Retorna (payload_json, status_http).
    """
    mensagem_texto = _extrair_texto_mensagem(dados_webhook)
    telemovel_remetente = _extrair_telemovel_remetente(dados_webhook)

    resposta_sim = "SIM" in mensagem_texto
    resposta_nao = "NÃO" in mensagem_texto or "NAO" in mensagem_texto

    if not telemovel_remetente or (not resposta_sim and not resposta_nao):
        return {"status": "ignorado", "motivo": "Mensagem não é aceitável."}, 200

    cliente_alvo = Agendamentos.query.filter(
        Agendamentos.telemovel == telemovel_remetente,
        Agendamentos.status == STATUS_EM_PROPOSTA,
    ).order_by(Agendamentos.data).first()

    if not cliente_alvo:
        return {"status": "erro", "motivo": "Nenhum agendamento ativo encontrado para este número"}, 404

    if resposta_nao:
        return _processar_recusa(cliente_alvo), 200
    return _processar_confirmacao(cliente_alvo)


def _extrair_texto_mensagem(dados_webhook: dict) -> str:
    message_obj = dados_webhook.get("data", {}).get("message", {})
    if "conversation" in message_obj:
        return message_obj.get("conversation", "").strip().upper()
    if "extendedTextMessage" in message_obj:
        return message_obj.get("extendedTextMessage", {}).get("text", "").strip().upper()
    return ""


def _extrair_telemovel_remetente(dados_webhook: dict) -> str:
    key_obj = dados_webhook.get("data", {}).get("key", {})
    remote_jid = key_obj.get("remoteJidAlt") or key_obj.get("remoteJid", "")
    if not remote_jid:
        return ""
    numero_puro = remote_jid.split("@")[0].strip()
    return numero_puro[-9:] if len(numero_puro) >= 9 else numero_puro


def _processar_recusa(cliente_alvo: Agendamentos) -> dict:
    print(f"❌ [WEBHOOK] O cliente {cliente_alvo.nome} recusou a vaga de imediato. A passar ao próximo...")

    vaga_original = Agendamentos.query.filter_by(
        hora=cliente_alvo.hora,
        barbeiro=cliente_alvo.barbeiro,
        status=STATUS_CANCELADO,
    ).order_by(Agendamentos.data).first()

    id_cliente_proposto = cliente_alvo.id
    cliente_alvo.status = STATUS_ATIVO
    cliente_alvo.canal = CANAL_RECUSADO
    db.session.commit()

    cancelar_job_timeout(id_cliente_proposto)

    try:
        whatsapp.enviar_texto(
            whatsapp.normalizar_telemovel(cliente_alvo.telemovel),
            whatsapp.mensagem_feedback_recusa(cliente_alvo),
            delay_ms=1000,
        )
        print(f"[WEBHOOK] Mensagem de cortesia enviada para {cliente_alvo.nome} (Recusa).")
    except Exception as erro:
        print(f"⚠️ [WEBHOOK] Falha ao enviar mensagem de cortesia do NÃO: {erro}")

    if vaga_original:
        executar_algoritmo_caca_vagas(id_agendamento=vaga_original.id)

    return {"status": "sucesso", "mensagem": "Recusa processada e vaga passada ao próximo cliente."}


def _processar_confirmacao(cliente_alvo: Agendamentos) -> tuple[dict, int]:
    try:
        vaga_disponivel = Agendamentos.query.with_for_update().filter_by(
            hora=cliente_alvo.hora,
            barbeiro=cliente_alvo.barbeiro,
            status=STATUS_CANCELADO,
        ).order_by(Agendamentos.data).first()

        if not vaga_disponivel:
            # A vaga já foi preenchida no site público entretanto
            print("⏳ Bloqueado! A vaga já foi ocupada manualmente pelo barbeiro.")
            cliente_alvo.status = STATUS_ATIVO
            db.session.commit()
            return {"status": "Esgotado", "motivo": "A vaga de antecipação já foi preenchida ou o tempo expirou."}, 200

        data_antiga = cliente_alvo.data
        data_nova = vaga_disponivel.data
        hora_corte = cliente_alvo.hora
        id_cliente_proposto = cliente_alvo.id

        # A vaga cancelada passa a ser do cliente que aceitou
        vaga_disponivel.nome = cliente_alvo.nome
        vaga_disponivel.telemovel = cliente_alvo.telemovel
        vaga_disponivel.servico = cliente_alvo.servico
        vaga_disponivel.canal = cliente_alvo.canal
        vaga_disponivel.status = STATUS_ATIVO

        # O horário antigo do cliente fica livre (cancelado) para reativar o ciclo
        cliente_alvo.status = STATUS_CANCELADO
        cliente_alvo.nome = None
        cliente_alvo.telemovel = None

        db.session.commit()

        print(f"\n⚡ [SUCESSO!] Cliente {vaga_disponivel.nome} antecipado com sucesso!")
        print(f"De: {data_antiga} -> Para: {data_nova} às {hora_corte}\n")

        _registar_historico_caca_vagas(vaga_disponivel, hora_corte)

        cancelar_job_timeout(id_cliente_proposto)

        # O horário antigo do cliente entra agora no ciclo de caça-vagas
        executar_algoritmo_caca_vagas(id_agendamento=id_cliente_proposto)

        dados_sucesso = {
            "nome": vaga_disponivel.nome,
            "telemovel": vaga_disponivel.telemovel,
            "data": data_nova,
            "hora": hora_corte,
            "barbeiro": vaga_disponivel.barbeiro,
            "servico": vaga_disponivel.servico,
            "canal": vaga_disponivel.canal,
        }
        whatsapp.enviar_alerta_troca_concluida(dados_sucesso)

        return {"status": "sucesso", "mensagem": "Agendamento antecipado automaticamente"}, 200

    except Exception as erro:
        db.session.rollback()
        print(f"❌ Erro crítico na transação do Caça-Vagas: {erro}")
        return {"status": "erro", "motivo": "Erro interno ao processar banco de dados"}, 500


def _registar_historico_caca_vagas(agendamento: Agendamentos, hora_corte: str) -> None:
    """Auditoria financeira: regista a faturação recuperada pelo Caça-Vagas."""
    try:
        registo = HistoricoCacaVagas(
            data_recuperacao=date.today().isoformat(),
            nome_cliente=agendamento.nome,
            barbeiro=agendamento.barbeiro,
            horario_recuperado=hora_corte,
            valor=preco_do_servico(agendamento.servico),
        )
        db.session.add(registo)
        db.session.commit()
        print(f"📊 [AUDITORIA] Sucesso registado: {agendamento.nome} poupou {registo.valor}€ à barbearia!")
    except Exception as erro:
        print(f"⚠️ [AUDITORIA] Erro na gravação do histórico financeiro: {erro}")


def preco_do_servico(servico: str) -> float:
    """Preço do serviço em euros, com fallback para valores legados/desconhecidos."""
    nome = str(servico or "").strip().lower()
    precos = {chave.lower(): valor for chave, valor in PRECOS_SERVICOS.items()}
    if nome in precos:
        return precos[nome]
    for chave, preco in precos.items():
        if chave in nome:
            return preco
    return PRECO_PADRAO


# ---------------------------------------------------------------------------
# Painel de administração
# ---------------------------------------------------------------------------

def montar_contexto_dashboard(data_str: str, barbeiro_filtro: str) -> dict:
    """Agrega todos os dados necessários para o template do dashboard."""
    hoje = datetime.now()
    data_hoje_crua = hoje.strftime(FORMATO_DATA)
    data_selecionada = (data_str or data_hoje_crua).strip()

    try:
        data_obj = datetime.strptime(data_selecionada, FORMATO_DATA)
    except ValueError:
        data_obj = hoje
        data_selecionada = data_hoje_crua

    data_exibicao = f"{data_obj.day} de {MESES_PT[data_obj.month]}, {data_obj.year}"

    query_ativos = Agendamentos.query.filter_by(data=data_selecionada, status=STATUS_ATIVO)
    if barbeiro_filtro:
        query_ativos = query_ativos.filter_by(barbeiro=barbeiro_filtro)

    return {
        "agendamentos": query_ativos.order_by(Agendamentos.hora).all(),
        "filtro_atual": barbeiro_filtro,
        "total_hoje": Agendamentos.query.filter_by(
            data=data_selecionada, status=STATUS_ATIVO
        ).count(),
        "total_whatsapp": Agendamentos.query.filter_by(
            data=data_selecionada, canal="whatsapp", status=STATUS_ATIVO
        ).count(),
        "data_hoje": data_exibicao,
        "data_hoje_crua": data_selecionada,
        "data_atual_sistema": data_hoje_crua,
    }


def montar_relatorio() -> dict:
    """Dados do relatório de faturação recuperada pelo Caça-Vagas."""
    historico = HistoricoCacaVagas.query.order_by(HistoricoCacaVagas.id.desc()).all()
    return {
        "historico": historico,
        "total_antecipacoes": len(historico),
        "total_faturado": sum(r.valor for r in historico),
    }
