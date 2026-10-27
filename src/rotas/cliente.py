import hmac
import re
import requests
import random
import os
from datetime import datetime
from flask import Blueprint, jsonify, render_template, request, redirect, url_for
from src import db
from src.models import Agendamentos
from src import csrf
from flask_wtf.csrf import CSRFProtect

# Inicializa o Blueprint do cliente público
cliente_bp = Blueprint('cliente', __name__)

#Lista com TODAS as horas por padrão
from src.constants import HORARIOS

@cliente_bp.route('/')
def index() -> str:
    """Rota raiz que serve a interface pública de agendamento."""
    data_atual = datetime.now().strftime('%Y-%m-%d')
    return render_template('cliente/agendamentos.html', horarios=HORARIOS, data_atual_sistema=data_atual)

@cliente_bp.route('/agendar', methods=['POST'])
def agendamento():
    """Recebe e valida e dispara o alerta personalizado contra no-shows."""

    agora_validacao = datetime.now()
    hoje_str = agora_validacao.strftime('%Y-%m-%d')
    hora_agora_str = agora_validacao.strftime('%H:%M')

    #Captura de todas as variáveis do formulário HTML de forma segura
    servico_escolhido: str = request.form.get('servico', '')
    data_escolhida: str = request.form.get('data', '')
    barbeiro_escolhido: str = request.form.get('barbeiro', '')
    hora_escolhida: str = request.form.get('hora', '')
    nome_cliente: str = request.form.get('nome', '').strip()
    telemovel: str = request.form.get('telemovel', '').strip()
    telemovel_limpo = re.sub(r'\D', '', telemovel)
    canal_notificacao: str = request.form.get('canal', 'whatsapp')

    if data_escolhida < hoje_str or (data_escolhida == hoje_str and hora_escolhida <= hora_agora_str):
        return "<h1>Erro: Não é permitido efetuar agendamentos para datas ou horários passados!</h1>", 400

    if not re.match(r"^9[12367]\d{7}$", telemovel_limpo):
        return "<h1>Erro: O número de telemóvel introduzido é inválido. Certifique-se de que tem 9 dígitos e começa por 91, 92, 93, 96 ou 97!</h1>", 400

    #Validação rigorosa no Backend
    if not all ([servico_escolhido, data_escolhida, barbeiro_escolhido, hora_escolhida, nome_cliente, telemovel]):
        return "Erro: Todos os campos obrigatórios devem ser preenchidos.", 400

    #Define dinamicamente o barbeiro no PostgreSQL
    if barbeiro_escolhido == "qualquer":
        # Verifica quem está ocupado nessa hora específica
        ocupado_bruno = Agendamentos.query.filter_by(data=data_escolhida, hora=hora_escolhida, barbeiro='barbeiro_1',
                                                     status='ativo').first()
        ocupado_matheus = Agendamentos.query.filter_by(data=data_escolhida, hora=hora_escolhida, barbeiro='barbeiro_2',
                                                       status='ativo').first()

        if ocupado_bruno and ocupado_matheus:
            return "<h1>Erro: Este horário acabou de ser preenchido. Por favor, escolha outra hora!</h1>", 400
        elif ocupado_bruno:
            barbeiro_final = "barbeiro_2"  # Vai para o Matheus
        elif ocupado_matheus:
            barbeiro_final = "barbeiro_1"  # Vai para o Bruno
        else:
            # Ambos estão livres: distribui de forma justa e aleatória
            barbeiro_final = random.choice(["barbeiro_1", "barbeiro_2"])
    else:
        barbeiro_final = barbeiro_escolhido

        # PROTEÇÃO CONTRA COLISÃO DE ÚLTIMA HORA (Anti-Duplicação síncrona)
        colisao = Agendamentos.query.filter_by(
            data=data_escolhida,
            hora=hora_escolhida,
            barbeiro=barbeiro_final,
            status='ativo'
        ).first()

        if colisao:
            return "<h1>Erro: Este horário acabou de ser preenchido por outro cliente há poucos segundos!</h1>", 400

    # Gravação segura e definitiva no PostgreSQL
    novo_agendamento = Agendamentos(
        data=data_escolhida,
        barbeiro=barbeiro_final,
        hora=hora_escolhida,
        nome=nome_cliente,
        telemovel=telemovel,
        servico=servico_escolhido,
        canal=canal_notificacao,
        status='ativo'
    )
    db.session.add(novo_agendamento)
    db.session.commit()
    #Captura o ID real gerado pela base de dados PostgreSQL
    id_gerado = novo_agendamento.id
    token_gerado = novo_agendamento.token_cancelamento

    dados_notificacao = {
        "id": id_gerado,
        "data": data_escolhida,
        "barbeiro": barbeiro_final,
        "hora": hora_escolhida,
        "nome": nome_cliente,
        "telemovel": telemovel,
        "servico": servico_escolhido,
        "canal": canal_notificacao,
        "token_cancelamento": token_gerado
    }
    disparar_notificacao_inteligente(dados_notificacao, origem="ONLINE")

    return render_template(
        'cliente/sucesso.html',
        nome_cliente=nome_cliente,
        servico_escolhido=servico_escolhido,
        data_escolhida=data_escolhida,
        hora_escolhida=hora_escolhida,
        canal_notificacao=canal_notificacao
    )

def disparar_notificacao_inteligente(agendamento: dict, origem: str = "ONLINE"):
    """Motor Único de Notificações da BF Barbearia (Usado por Clientes e Admin)"""

    canal_notificacao = agendamento.get('canal', 'whatsapp')
    if canal_notificacao in ['nenhum', 'sms']:
        print(f"➔ [{origem}] Nenhuma notificação digital agendada por opção do cliente/sistema.")
        return

    token_seguro = agendamento.get('token_cancelamento', '')
    URL_SaaS = os.getenv("URL_PUBLICO_SaaS", "http://bf-barbearia.onrender.com")
    link_cancelamento = f"{URL_SaaS}/cancelar_vaga/{token_seguro}"

    nome_cliente = agendamento.get('nome', '')
    servico_escolhido = agendamento.get('servico', 'Serviço')
    data_escolhida = agendamento.get('data', '')
    hora_escolhida = agendamento.get('hora', '')
    barbeiro_escolhido = agendamento.get('barbeiro', '')
    telemovel = agendamento.get('telemovel', '')

    #Mapeamento estético dos nomes dos profissionais
    nome_barbeiro_formatado = "Bruno Ferreira" if barbeiro_escolhido == "barbeiro_1" else "Matheus Santos"
    if barbeiro_escolhido == "qualquer":
        nome_barbeiro_formatado = "Equipa BF"

    print(f"\n➔[{origem}] A processar envio via {canal_notificacao.upper()}")

    servico_formatado = servico_escolhido.replace('+', ' + ').upper().strip()

    telemovel_limpo = re.sub(r'\D', '', telemovel)
    if not telemovel_limpo.startswith('351') and len(telemovel_limpo) == 9:
        telemovel_api = f"351{telemovel_limpo}"
    else:
        telemovel_api = telemovel_limpo

    if canal_notificacao == "whatsapp":
        mensagem_whatsapp = (
            f"Olá {nome_cliente}! 👋\n\n"
            f"O teu corte de **{servico_formatado}** está confirmado na **BF Barbearia**! 💈\n"
            f"📅 Data: {data_escolhida}\n"
            f"⏰ Hora: {hora_escolhida}\n"
            f"✂️ Profissional: {nome_barbeiro_formatado}\n\n"
            f"Se precisares de alterar ou cancelar, clica aqui até 2h antes:\n{link_cancelamento}\n\n"
            f"Até já! 🔥"
        )
        print("------------------------------------------")
        print(mensagem_whatsapp)
        print("------------------------------------------")

        API_BASE = os.getenv("EVOLUTION_API_URL", "https://obtuse-pasty-traitor.ngrok-free.dev/message/sendText/BF-Barbearia")
        API_BASE_CLEAN = API_BASE.replace("/message/sendText/BF-Barbearia", "").rstrip('/')
        URL_EVOLUTION = f"{API_BASE_CLEAN}/message/sendText/BF-Barbearia"
        API_KEY_EVOLUTION = os.getenv("EVOLUTION_API_KEY", os.getenv("FLASK_SECRET_KEY", ""))

        payload = {
            "number": telemovel_api,
            "text": mensagem_whatsapp,
            "options": {
                "delay": 1200,  # Simula digitação humana para proteção do teu número
                "presence": "composing"
            }
        }

        headers = {
            "apikey": API_KEY_EVOLUTION,
            "Content-Type": "application/json"
        }

        try:
            # Faz o disparo HTTP local para o motor Node.js enviar para o teu telemóvel
            resposta = requests.post(URL_EVOLUTION, json=payload, headers=headers, timeout=6)

            if resposta.status_code in [200, 201]:
                print(f"🚀 [WHATSAPP REAL] Mensagem entregue com sucesso para {nome_cliente} ({telemovel_api})")
            else:
                print(
                    f"⚠️ [FALHA WHATSAPP] Servidor recusou. Status: {resposta.status_code}. Resposta: {resposta.text}")
        except requests.exceptions.RequestException as erro:
            print(f"❌ [ERRO CRÍTICO API] Impossível comunicar com a Evolution API local: {erro}")

    print(f"\n[SUCESSO] Horário {hora_escolhida} bloqueado para {barbeiro_escolhido} no dia {data_escolhida}.\n")

    #Captura de dados pronta para ser enviada para a Base de Dados.
    print(f"\n========[REGISTO DE SISTEMA - {origem}]========")
    print(f"Cliente: {nome_cliente} ({telemovel_api})")
    print(f"Serviço: {servico_formatado}")
    print(f"Profissional: {barbeiro_escolhido.replace('_', '').title()}")
    print(f"Data/Hora: {data_escolhida} às {hora_escolhida}")
    print(f"Canal de Alerta: Enviar lembrete automático via {canal_notificacao.upper()}")
    print("="*42)

@cliente_bp.route('/verificar-disponibilidade')
def verificar_disponibilidade():
    """API reativa que consulta o PostgreSQL em tempo real para saber os horários livres"""
    data_req = request.args.get('data', '')
    barbeiro_req = request.args.get('barbeiro', '')

    if not data_req or not barbeiro_req:
        return jsonify(HORARIOS)

    agora = datetime.now()
    data_hoje_str = agora.strftime('%Y-%m-%d')
    hora_atual_str = agora.strftime('%H:%M')

    # CONSULTAS POSTGRESQL: Procuramos apenas agendamentos ativos para calcular as vagas livres
    if barbeiro_req != "qualquer":
        agendamentos_ocupados = Agendamentos.query.filter_by(
            data=data_req, barbeiro=barbeiro_req, status='ativo'
        ).all()
        horas_ocupadas = [m.hora for m in agendamentos_ocupados]
        horarios_livres = [hora for hora in HORARIOS if hora not in horas_ocupadas]
    else:
        # Lógica contra colisões para a opção 'Qualquer Um'
        ocupadas_bruno = [m.hora for m in Agendamentos.query.filter_by(data=data_req, barbeiro='barbeiro_1', status='ativo').all()]
        ocupadas_matheus = [m.hora for m in Agendamentos.query.filter_by(data=data_req, barbeiro='barbeiro_2', status='ativo').all()]

        hora_cheia = [
            hora for hora in HORARIOS
            if hora in ocupadas_bruno and hora in ocupadas_matheus
        ]

        #Filtragem total da lista, mantendo apenas os horarios livres
        horarios_livres = [hora for hora in HORARIOS if hora not in hora_cheia]

    #Bloqueio de agendamentos no passado
    if data_req < data_hoje_str:
        horarios_livres = []
    elif data_req == data_hoje_str:
        horarios_livres = [hora for hora in horarios_livres if hora > hora_atual_str]

    #Bloqueia Domingos e Segundas-Feiras
    try:
        data_objeto = datetime.strptime(data_req, '%Y-%m-%d')
        dia_da_semana = data_objeto.weekday()
        if dia_da_semana == 6 or dia_da_semana == 0:
            horarios_livres = []
    except ValueError:
        pass

    return jsonify(horarios_livres)

@cliente_bp.route('/webhook/confirmar-antecipacao', methods=['POST'])
def confirmar_antecipacao():
    """Recebe a resposta 'SIM' via Webhook do WhatsApp/SMS, localiza o cliente pelo telemóvel e efetua a troca automática de horário no PostgreSQL."""

    token_recebido = request.headers.get('X-Webhook-Token', '')
    token_oficial = os.getenv('WEBHOOK_TOKEN', "")
    if not token_oficial or not hmac.compare_digest(token_recebido, token_oficial):
        return jsonify({"status": "erro", "motivo": "Não autorizado"}), 403

    dados_webhook = request.get_json(silent=True) or {}

    #Extrai os dados no formato nativo da Evolution API v2
    data_obj = dados_webhook.get('data', {})
    message_obj = data_obj.get('message', {})

    #Captura o texto da mensagem
    mensagem_texto = ""
    if "conversation" in message_obj:
        mensagem_texto = message_obj.get('conversation', '').strip().upper()
    elif 'extendedTextMessage' in message_obj:
        mensagem_texto = message_obj.get('extendedTextMessage', {}).get('text', '').strip().upper()

    #Captura o JID (JabberID) do remetente
    key_obj = data_obj.get('key', {})
    remote_jid = key_obj.get('remoteJidAlt') or key_obj.get('remoteJid', '')

    #Limpa o JID para obter apenas os número do telemóvel
    telemovel_remetente = ""
    if remote_jid:
        numero_puro = remote_jid.split('@')[0].strip()
        telemovel_remetente = numero_puro[-9:] if len(numero_puro) >= 9 else numero_puro

    resposta_sim = "SIM" in mensagem_texto
    resposta_nao = "NÃO" in mensagem_texto or "NAO" in mensagem_texto

    if not telemovel_remetente or (not resposta_sim and not resposta_nao):
        return jsonify({"status": "ignorado", "motivo": "Mensagem não é aceitável."}), 200

    #Procura pelo agendamento ATIVO deste cliente (o mais próximo no futuro)
    cliente_alvo = Agendamentos.query.filter(
        Agendamentos.telemovel == telemovel_remetente,
        Agendamentos.status == "em_proposta",
    ).order_by(Agendamentos.data).first()

    if not cliente_alvo:
        return jsonify({"status": "erro", "motivo": "Nenhum agendamento ativo encontrado para este número"}), 404

    #Cenário Rejeição
    if resposta_nao:
        print(f"❌ [WEBHOOK] O cliente {cliente_alvo.nome} recusou a vaga de imediato. A passar ao próximo...")

        #Guardamos os dados da vaga proposta que estão no slot cancelado antes de alterar o cliente
        vaga_original = Agendamentos.query.filter_by(
            hora=cliente_alvo.hora,
            barbeiro=cliente_alvo.barbeiro,
            status='cancelado'
        ).order_by(Agendamentos.data).first()

        #Reverte o cliente para 'ativo' no seu horário original
        id_cliente_proposto = cliente_alvo.id
        cliente_alvo.status = 'recusado_ciclo'
        db.session.commit()

        #Cancelamento do temporizador após recessão de resposta do cliente
        from src import scheduler
        try:
            scheduler.remove_job(f"timeout_caca_vagas_{id_cliente_proposto}")
        except Exception:
            pass

        #Mensagem de agradecimento pela resposta
        try:
            API_BASE = os.getenv("EVOLUTION_API_URL", "https://obtuse-pasty-traitor.ngrok-free.dev")
            API_BASE_CLEAN = API_BASE.replace("/message/sendText/BF-Barbearia", "").rstrip('/')
            url_feedback = f"{API_BASE_CLEAN}/message/sendText/BF-Barbearia"
            API_KEY_EVOLUTION = os.getenv("EVOLUTION_API_KEY", os.getenv("FLASK_SECRET_KEY", ""))

            telemovel_limpo = re.sub(r'\D', '', cliente_alvo.telemovel)
            telemovel_api = f"351{telemovel_limpo}" if len(telemovel_limpo) == 9 else telemovel_limpo
            texto_feedback_nao = (
                f"Obrigado pela tua resposta, {cliente_alvo.nome}! 👍\n\n"
                f"Fica descansado, o teu corte mantém-se rigorosamente agendado para "
                f"**dia {cliente_alvo.data} às {cliente_alvo.hora}**. Vemo-nos brevemente! 💈"
            )

            payload_feedback = {
                "number": telemovel_api,
                "options": {"delay": 1000, "presence": "composing"},
                "text": texto_feedback_nao
            }
            headers_feedback = {"apikey": API_KEY_EVOLUTION, "Content-Type": "application/json"}

            #Disparo de cortesia
            requests.post(url_feedback, json=payload_feedback, headers=headers_feedback, timeout=5)
            print(f"[WEBHOOK] Mensagem de cortesia enviada para {cliente_alvo.nome} (Recusa).")
        except Exception as e_feedback:
            print(f"⚠️ [WEBHOOK] Falha ao enviar mensagem de cortesia do NÃO: {e_feedback}")

        #Dispara o algoritmo para o próximo candidato da fila
        if vaga_original:
            from src.rotas.admin import executar_algoritmo_caca_vagas
            executar_algoritmo_caca_vagas(id_agendamento=vaga_original.id)

        return jsonify({"status": "sucesso", "mensagem": "Recusa processada e vaga passada ao próximo cliente."}), 200


    try:
        vaga_disponivel = Agendamentos.query.with_for_update().filter_by(
            hora=cliente_alvo.hora,
            barbeiro=cliente_alvo.barbeiro,
            status='cancelado'
        ).order_by(Agendamentos.data).first()

        if not vaga_disponivel:
        #Caso a vaga já tenha sido preenchida no site público
            print(f"⏳ Bloqueado! A vaga já foi ocupada manualmente pelo barbeiro.")
            cliente_alvo.status = 'ativo'
            db.session.commit()
            return jsonify({"status": "Esgotado", "motivo": "A vaga de antecipação já foi preenchida ou o tempo expirou."}), 200

        #Armazenamento de dados para o LOG e NOTIFICAÇÃO
        data_antiga = cliente_alvo.data
        data_nova = vaga_disponivel.data
        hora_corte = cliente_alvo.hora
        id_cliente_proposto = cliente_alvo.id

        # A vaga que estava cancelada passa a ser do cliente que aceitou
        vaga_disponivel.nome = cliente_alvo.nome
        vaga_disponivel.telemovel = cliente_alvo.telemovel
        vaga_disponivel.servico = cliente_alvo.servico
        vaga_disponivel.canal = cliente_alvo.canal
        vaga_disponivel.status = 'ativo'

        # O horário antigo do cliente é libertado (fica marcado como cancelado para reativar o ciclo)
        cliente_alvo.status = 'cancelado'
        cliente_alvo.nome = None
        cliente_alvo.telemovel = None

        db.session.commit()

        print(f"\n⚡ [SUCESSO!] Cliente {vaga_disponivel.nome} antecipado com sucesso!")
        print(f"De: {data_antiga} -> Para: {data_nova} às {hora_corte}\n")

        #📊 ✅ REGISTO DE FATURAÇÃO RECUPERADA DINÂMICA

        try:
            from src.models import HistoricoCacaVagas
            from datetime import date

            preco_servico = 15.0 #Padrão de fallback caso a string mude
            servico_limpo = str(vaga_disponivel.servico).lower().strip()

            if "corte+barba+sobrancelha" in servico_limpo or "19" in servico_limpo:
                preco_servico = 19.0
            elif "corte+barba" in servico_limpo or "18" in servico_limpo:
                preco_servico = 18.0
            elif "corte+bigode+sobrancelha" in servico_limpo or "15" in servico_limpo:
                preco_servico = 15.0
            elif "corte+sobrancelha" in servico_limpo or "14" in servico_limpo:
                preco_servico = 14.0
            elif "corte zero+barba" in servico_limpo or "corte de cabelo" in servico_limpo or "13" in servico_limpo:
                preco_servico = 13.0
            elif "corte m60" in servico_limpo or "10" in servico_limpo:
                preco_servico = 10.0
            elif "barba" in servico_limpo or "7" in servico_limpo:
                preco_servico = 7.0

            novo_registo_sucesso = HistoricoCacaVagas(
                data_recuperacao=date.today().isoformat(),
                nome_cliente=vaga_disponivel.nome,
                barbeiro=vaga_disponivel.barbeiro,
                horario_recuperado=hora_corte,
                valor=preco_servico,
            )
            db.session.add(novo_registo_sucesso)
            db.session.commit()
            print(f"📊 [AUDITORIA] Sucesso registado: {vaga_disponivel.nome} poupou {preco_servico}€ à barbearia!")
        except Exception as e_auditoria:
            print(f"⚠️ [AUDITORIA] Erro na gravação do histórico financeiro: {e_auditoria}")

        from src import scheduler
        try:
            scheduler.remove_job(f"timeout_caca_vagas_{id_cliente_proposto}")
        except Exception: pass

        #Cenário Confirmação
        #Dispara uma confirmação de sucesso para o telemovel do cliente
        from src.rotas.admin import executar_algoritmo_caca_vagas
        executar_algoritmo_caca_vagas(id_agendamento=id_cliente_proposto)

        dados_sucesso = {
            "nome": vaga_disponivel.nome,
            "telemovel": vaga_disponivel.telemovel,
            "data": data_nova,
            "hora": hora_corte,
            "barbeiro": vaga_disponivel.barbeiro,
            "servico": vaga_disponivel.servico,
            "canal": vaga_disponivel.canal
        }

        # Função auxiliar para enviar a mensagem de parabéns
        enviar_alerta_troca_concluida(dados_sucesso)

        return jsonify({"status": "sucesso", "mensagem": "Agendamento antecipado automaticamente"}), 200

    except Exception as erro:
        db.session.rollback()
        print(f"❌ Erro crítico na transação do Caça-Vagas: {erro}")
        return jsonify({"status": "erro", "motivo": "Erro interno ao processar banco de dados"}), 500


def enviar_alerta_troca_concluida(agendamento: dict):
    """Envia o comprovativo de que o horário foi alterado com sucesso pelo motor"""
    import os
    import requests
    nome_barbeiro = "Bruno Ferreira" if agendamento['barbeiro'] == "barbeiro_1" else "Matheus Santos"

    API_BASE = os.getenv("EVOLUTION_API_URL", "https://obtuse-pasty-traitor.ngrok-free.dev")
    NOME_INSTANCIA = "BF-Barbearia"
    API_KEY = os.getenv("FLASK_SECRET_KEY", "chave_local")

    endpoint = f"{API_BASE}/message/sendText/{NOME_INSTANCIA}"

    headers = {
        "Content-Type": "application/json",
        "apikey": API_KEY
    }

    #Construção da Mensagem Premium
    texto_mensagem = (
        f"Concluído com sucesso, {agendamento['nome']}! 🔥\n\n"
        f"O teu horário foi alterado automaticamente no sistema da **BF Barbearia**. 🚀\n"
        f"Esperamos por ti no novo dia **{agendamento['data']} às {agendamento['hora']}** com o barbeiro {nome_barbeiro}.\n\n"
        f"O teu horário antigo foi libertado. Obrigado por nos ajudar a manter a agenda cheia! 💈"
    )

    #Garante que o número tem sufixo correto para o WhatsApp
    numero_destino = agendamento['telemovel']
    numero_limpo = "".join(filter(str.isdigit, str(numero_destino)))

    if len(numero_limpo) == 9:
        jid_final = f"351{numero_limpo}@s.whatsapp.net"
    else:
        jid_final = f"{numero_limpo}@s.whatsapp.net"

    payload = {
        "number": jid_final,
        "options": {
            "delay": 1200,  # Pequeno delay de 1.2 segundos para parecer humano
            "presence": "composing"
        },
        "text": texto_mensagem
        }

    #Envio do pedido HTTP
    try:
        print(f"\n➔ [MOTOR] A disparar WhatsApp real de sucesso para {agendamento['nome']} ({jid_final})...")

        resposta = requests.post(endpoint, json=payload, headers=headers, timeout=10)

        if resposta.status_code in [200, 201]:
            print(f"✅ [WHATSAPP] Mensagem de troca concluída entregue com sucesso!")
        else:
            print(f"⚠️ [WHATSAPP] Erro no envio. Código: {resposta.status_code} | Resposta: {resposta.text}")

    except Exception as erro:
        print(f"❌ [ERRO CRÍTICO] Falha de rede ao comunicar com a Evolution API: {erro}")

@cliente_bp.route('/cancelar_vaga/<string:token>', methods=['GET', 'POST'])
def cancelamento_publico(token: str):
    """Página pública que permite ao cliente cancelar o seu próprio corte e ativa o Caça-Vagas."""

    from src.rotas.admin import executar_algoritmo_caca_vagas

    #Procura o agendamento ativo no PostgreSQL pelo Token
    agendamento = Agendamentos.query.filter_by(token_cancelamento=token, status='ativo').first_or_404()

    if request.method == 'POST':
        #Captura os dados antes de cancelar para o ecrã de sucesso
        nome_cliente = agendamento.nome
        data_corte = agendamento.data
        hora_corte = agendamento.hora
        id_agendamento = agendamento.id

        #Reutilização
        executar_algoritmo_caca_vagas(id_agendamento)

        return render_template('cliente/cancelado_post.html', nome=nome_cliente, data_corte=data_corte, hora=hora_corte)

    return render_template('cliente/cancelar_get.html', agendamento=agendamento)