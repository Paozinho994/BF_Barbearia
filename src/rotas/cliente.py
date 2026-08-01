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
    return render_template('cliente/agendamentos.html', horarios=HORARIOS)

@cliente_bp.route('/agendar', methods=['POST'])
def agendamento():
    """Recebe e valida e dispara o alerta personalizado contra no-shows."""

    #Captura de todas as variáveis do formulário HTML de forma segura
    servico_escolhido: str = request.form.get('servico', '')
    data_escolhida: str = request.form.get('data', '')
    barbeiro_escolhido: str = request.form.get('barbeiro', '')
    hora_escolhida: str = request.form.get('hora', '')
    nome_cliente: str = request.form.get('nome', '').strip()
    telemovel: str = request.form.get('telemovel', '').strip()
    canal_notificacao: str = request.form.get('canal', 'whatsapp')

    #Validação rigorosa no Backend
    if not all ([servico_escolhido, data_escolhida, barbeiro_escolhido, hora_escolhida, nome_cliente, telemovel]):
        return "Erro: Todos os campos obrigatórios devem ser preenchidos.", 400

    novo_agendamento = Agendamentos(
        data=data_escolhida,
        barbeiro=barbeiro_escolhido,
        hora=hora_escolhida,
        nome=nome_cliente,
        telemovel=telemovel,
        servico=servico_escolhido,
        canal=canal_notificacao,
        status='ativo'
    )
    db.session.add(novo_agendamento)
    db.session.commit()

    dados_notificacao = {
        "data": data_escolhida,
        "barbeiro": barbeiro_escolhido,
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

    if canal_notificacao == "whatsapp":
        mensagem_whatsapp = (
            f"Olá {nome_cliente}! 👋\n\n"
            f"O teu corte de **{servico_escolhido.replace('+', 'e').upper()}** está confirmado na **BF Barbearia**! 💈\n"
            f"📅 Data: {data_escolhida}\n"
            f"⏰ Hora: {hora_escolhida}\n"
            f"✂️ Profissional: {nome_barbeiro_formatado}\n\n"
            f"Se precisares de alterar ou cancelar, clica aqui até 4h antes: http://bfbarber.pt\n"
            f"Até já! 🔥"
        )
        print("------------------------------------------")
        print(mensagem_whatsapp)
        print("------------------------------------------")

    else:
        mensagem_sms = (
            f"BF Barbearia: Marcacao confirmada para {nome_cliente}. "
            f"{servico_escolhido.split()[0]} no dia {data_escolhida} as {hora_escolhida} com {nome_barbeiro_formatado}. "
            f"Para alterar ligue p/ a barbearia."
        )
        print("------------------------------------------")
        print(mensagem_sms)
        print("------------------------------------------")

    print(f"\n[SUCESSO] Horário {hora_escolhida} bloqueado para {barbeiro_escolhido} no dia {data_escolhida}.\n")

    #Captura de dados pronta para ser enviada para a Base de Dados.
    print(f"\n========[REGISTO DE SISTEMA - {origem}]========")
    print(f"Cliente: {nome_cliente} ({telemovel})")
    print(f"Serviço: {servico_escolhido.upper()}")
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

    return jsonify(horarios_livres)