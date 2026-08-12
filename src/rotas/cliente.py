import re
import requests
import random
from datetime import datetime
from flask import Blueprint, jsonify, render_template, request, redirect, url_for
from src import db
from src.models import Agendamentos

# Inicializa o Blueprint do cliente público
cliente_bp = Blueprint('cliente', __name__)

#Lista com TODAS as horas por padrão
HORARIOS = ["10:00", "10:30", "11:00", "11:30", "12:00", "12:30", "15:00", "15:30", "16:00", "16:30", "17:00", "17:30", "18:00", "18:30", "19:00", "19:30"]

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

    dados_notificacao = {
        "id": id_gerado,
        "data": data_escolhida,
        "barbeiro": barbeiro_final,
        "hora": hora_escolhida,
        "nome": nome_cliente,
        "telemovel": telemovel,
        "servico": servico_escolhido,
        "canal": canal_notificacao
    }
    disparar_notificacao_inteligente(dados_notificacao, origem="ONLINE")

    return render_template('cliente/sucesso.html')

def disparar_notificacao_inteligente(agendamento: dict, origem: str = "ONLINE"):
    """Motor Único de Notificações da BF Barbearia (Usado por Clientes e Admin)"""

    canal_notificacao = agendamento.get('canal', 'whatsapp')
    if canal_notificacao == 'nenhum':
        return

    id_agendamento = agendamento.get('id', 0)

    link_cancelamento = f"http://localhost:5000/cancelar-vaga/{id_agendamento}"

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

        URL_EVOLUTION = "https://obtuse-pasty-traitor.ngrok-free.dev/message/sendText/BF-Barbearia"
        import os
        API_KEY_EVOLUTION = os.getenv("FLASK_SECRET_KEY", "chave_local")

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
            resposta = requests.post(URL_EVOLUTION, json=payload, headers=headers, timeout=8)

            if resposta.status_code in [200, 201]:
                print(f"🚀 [WHATSAPP REAL] Mensagem entregue com sucesso para {nome_cliente} ({telemovel_api})")
            else:
                print(
                    f"⚠️ [FALHA WHATSAPP] Servidor recusou. Status: {resposta.status_code}. Resposta: {resposta.text}")
        except requests.exceptions.RequestException as erro:
            print(f"❌ [ERRO CRÍTICO API] Impossível comunicar com a Evolution API local: {erro}")

    else:
        mensagem_sms = (
            f"BF Barbearia: Marcacao confirmada para {nome_cliente}. "
            f"{servico_escolhido.split()[0]} no dia {data_escolhida} as {hora_escolhida} com {nome_barbeiro_formatado}. "
            f"Para alterar ou cancelar, ligue para a barbearia ou clique no link até 2h antes: {link_cancelamento}"
        )
        print("------------------------------------------")
        print(mensagem_sms)
        print("------------------------------------------")

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

@cliente_bp.route('/webhook/confrmar-antecipacao', methods=['POST'])
def confirmar_antecipacao():
    """Recebe a resposta 'SIM' via Webhook do WhatsApp/SMS, localiza o cliente pelo telemóvel e efetua a troca automática de horário no PostgreSQL."""

    dados = request.get_json() or {}

    #Captura o telemóvel de quem enviou a menagem e o texto
    telemovel_remetente = dados.get('telemovel', '').strip()
    mensagem_texto = dados.get('texto', '').strip().upper()

    if not telemovel_remetente or "SIM" not in mensagem_texto:
        return jsonify({"status": "ignorado", "motivo": "Mensagem não é aceitável."}), 200

    #Procura pelo agendamento ATIVO deste cliente (o mais próximo no futuro)
    cliente_alvo = Agendamentos.query.filter(
        Agendamentos.telemovel.like(f"%{telemovel_remetente}%"),
        Agendamentos.status == "ativo",
    ).order_by(Agendamentos.data).first()

    if not cliente_alvo:
        return jsonify({"status": "erro", "motivo": "Nenhum agendamento ativo encontrado para este número"}), 404

    vaga_disponivel = Agendamentos.query.filter_by(
        hora=cliente_alvo.hora,
        barbeiro=cliente_alvo.barbeiro,
        status='cancelado'
    ).order_by(Agendamentos.data).first()

    if not vaga_disponivel:
        #Caso a vaga já tenha sido preenchida no site público
        return jsonify({"status": "esgotado", "motivo": "A vaga de antecipação já foi preenchida por outro utilizador"}), 200

    #Armazenamento de dados para o LOG e NOTIFICAÇÃO
    data_antiga = cliente_alvo.data
    data_nova = vaga_disponivel.data
    hora_corte = cliente_alvo.hora

    #Transação no PostgreSQL
    try:
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

        #Dispara uma confirmação de sucesso para o telemovel do cliente
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
    nome_barbeiro = "Bruno Ferreira" if agendamento['barbeiro'] == "barbeiro_1" else "Matheus Santos"

    print(f"\n➔ [MOTOR] A enviar confirmação de antecipação para {agendamento['nome']}")
    print("------------------------------------------")
    print(
        f"Concluído com sucesso, {agendamento['nome']}! 🔥\n\n"
        f"O teu horário foi alterado automaticamente no sistema da **BF Barbearia**. 🚀\n"
        f"Esperamos por ti no novo dia **{agendamento['data']} às {agendamento['hora']}** com o barbeiro {nome_barbeiro}.\n\n"
        f"O teu horário antigo foi libertado. Obrigado por nos ajudar a manter a agenda cheia! 💈"
    )
    print("------------------------------------------")

@cliente_bp.route('/cancelar_vaga/<int:id_agendamento>', methods=['GET', 'POST'])
def cancelamento_publico(id_agendamento: int):
    """Página pública que permite ao cliente cancelar o seu próprio corte e ativa o Caça-Vagas."""

    from src.rotas.admin import executar_algoritmo_caca_vagas

    #Procura o agendamento ativo no PostgreSQL pelo ID
    agendamento = db.session.get(Agendamentos, id_agendamento)

    if not agendamento or agendamento.status != 'ativo':
        return "<h1 style='font-family:sans-serif; text-align:center; margin-top:5rem;'>⚠️ Esta marcação já não se encontra ativa ou não existe!</h1>", 400
    if request.method == 'POST':
        #Captura os dados antes de cancelar para o ecrã de sucesso
        nome_cliente = agendamento.nome
        data_corte = agendamento.data
        hora_corte = agendamento.hora

        #Reutilização
        executar_algoritmo_caca_vagas(id_agendamento)

        return f'''
        <div style="text-align: center; font-family: sans-serif; padding: 4rem; background: #0a0a0a; color: #fff; height: 100vh;">
            <h2 style="color: #22c55e;">Cancelado com Sucesso! ✅</h2>
            <p>Olá {nome_cliente}, o teu horário de dia {data_corte} às {hora_corte} foi libertado no sistema.</p>
            <p>Obrigado por avisares com antecedência! 💈</p>
            <br><a href="/" style="color: #f59e0b; text-decoration: none; font-weight: bold;">← Voltar ao Início</a>
        </div>
        '''

    #Ecrã GET
    return f'''
    <div style="text-align: center; font-family: sans-serif; padding: 3rem; background: #0a0a0a; color: #fff; height: 100vh; display: flex; flex-direction: column; justify-content: center; align-items: center;">
        <div style="background: #171717; padding: 2.5rem; border-radius: 12px; border: 1px solid #262626; max-width: 450px; width: 90%;">
            <h2 style="color: #f59e0b; margin-top: 0;">BF Barbearia</h2>
            <p style="color: #a3a3a3;">Olá <strong>{agendamento.nome}</strong>, confirmas o cancelamento do teu agendamento?</p>
            <p style="background: #262626; padding: 10px; border-radius: 6px; font-weight: bold;">📅 Dia: {agendamento.data} | ⏰ Hora: {agendamento.hora}</p>
            <form method="POST">
                <button type="submit" style="background: #dc2626; color: #fff; border: none; padding: 14px 28px; font-weight: bold; border-radius: 8px; cursor: pointer; width: 100%; font-size: 1rem;">
                    ❌ Confirmar Cancelamento Definitivo
                </button>
            </form>
        </div>
    </div>
    '''