import re
from flask import Blueprint, render_template, request, redirect, url_for
from datetime import datetime
from src import db
from src.models import Agendamentos
from src.rotas.cliente import HORARIOS, disparar_notificacao_inteligente


# Inicializa o Blueprint do administrador
admin_bp = Blueprint('admin', __name__)

@admin_bp.route('/')
def dashboard() -> str:
    """Renderiza o painel de administração principal"""
    barbeiro_filtro = request.args.get('barbeiro', '')

    #Gerador de data
    hoje = datetime.now()
    data_hoje_crua = hoje.strftime("%Y-%m-%d")
    data_selecionada_crua = request.args.get('data', data_hoje_crua).strip()

    try:
        data_obj = datetime.strptime(data_selecionada_crua, '%Y-%m-%d')
    except ValueError:
        data_obj = hoje

    meses = {
        1: "Janeiro", 2: "Fevereiro", 3: "Março", 4: "Abril", 5: "Maio", 6: "Junho",
        7: "Julho", 8: "Agosto", 9: "Setembro", 10: "Outubro", 11: "Novembro", 12: "Dezembro"
    }
    data_exibicao_formatada = f"{data_obj.day} de {meses[data_obj.month]}, {data_obj.year}"

    #Queries para Clientes ATIVOS
    query_ativos = Agendamentos.query.filter_by(data=data_selecionada_crua, status='ativo')
    if barbeiro_filtro:
        query_ativos = query_ativos.filter_by(barbeiro=barbeiro_filtro)

    total_hoje = Agendamentos.query.filter_by(data=data_selecionada_crua, status='ativo').count()
    total_whatsapp = Agendamentos.query.filter_by(data=data_selecionada_crua, canal='whatsapp', status='ativo').count()
    total_sms = Agendamentos.query.filter_by(data=data_selecionada_crua, canal='sms', status='ativo').count()

    #Ordem cronológica das horas de corte
    agendamentos_ordenados = query_ativos.order_by(Agendamentos.hora).all()

    #Queries de Histórico de Cancelados / No-Shows do Dia Selecionado
    query_cancelados = Agendamentos.query.filter_by(data=data_selecionada_crua, status='cancelado')
    if barbeiro_filtro:
        query_cancelados = query_cancelados.filter_by(barbeiro=barbeiro_filtro)

    cancelados_dia = query_cancelados.order_by(Agendamentos.hora).all()

    #Retorna os aagendamentos, o filtro ativo e a lista HORARIOS para o formulario manual
    return render_template(
        'admin/dashboard.html',
        agendamentos = agendamentos_ordenados,
        filtro_atual = barbeiro_filtro,
        horarios = HORARIOS,
        total_hoje = total_hoje,
        total_whatsapp = total_whatsapp,
        total_sms= total_sms,
        data_hoje=data_exibicao_formatada,
        data_hoje_crua=data_selecionada_crua,
        data_atual_sistema=data_hoje_crua
    )

@admin_bp.route('/marcar', methods=['POST'])
def criar_marcacao_manual():
    """Recebe e processa os dados do formulário de marcação manual."""

    #Captura os dados enviados pelo formulário HTML de forma segura
    nome_cliente: str = request.form.get('nome', '').strip()
    telemovel: str = request.form.get('telemovel', '').strip()
    hora_corte: str = request.form.get('hora', '')
    data_escolhida: str = request.form.get('data', '2026-07-28')
    barbeiro_escolhido: str = request.form.get('barbeiro', 'barbeiro_1')
    canal_notificacao: str = request.form.get('canal', 'nenhum')

    #Validação inicial simples
    if not nome_cliente or not telemovel or not hora_corte:
        return "Erro: Todos os campos são obrigatórios.", 400

    telemovel_limpo = re.sub(r'\D', '', telemovel)

    if not re.match(r"^9\d{8}$", telemovel_limpo):
        return (
            "<h1>Erro: O número de telemóvel introduzido no painel é inválido!</h1>"
            "<p>Certifique-se de que inseriu exatamente 9 dígitos e que o número começa por 9 (ex: 912345678).</p>"
            "<br><a href='javascript:history.back()'>← Voltar Atrás</a>",
            400
        )

    colisao = Agendamentos.query.filter_by(
        data=data_escolhida,
        hora=hora_corte,
        barbeiro=barbeiro_escolhido,
        status='ativo'
    ).first()

    if colisao:
        return f"<h1>Erro: O horário {hora_corte} para esta data já foi preenchido por outro cliente!</h1>", 400

    #Cria a marcação manual com o EXATO padrão de chaves de cliente.py
    nova_marcacao = Agendamentos(
        data=data_escolhida,
        barbeiro=barbeiro_escolhido,
        hora=hora_corte,
        nome=nome_cliente,
        telemovel=telemovel_limpo,
        servico="Marcação Manual (Telefone)",
        canal=canal_notificacao,
        status='ativo'
    )
    db.session.add(nova_marcacao)
    db.session.commit()

    dados_notificacao = {
        "data": data_escolhida, "barbeiro": barbeiro_escolhido, "hora": hora_corte,
        "nome": nome_cliente, "telemovel": telemovel, "servico": "Marcação Manual (Telefone)", "canal": canal_notificacao
    }
    disparar_notificacao_inteligente(dados_notificacao, origem="MANUAL/BALCÃO")

    return redirect(url_for('admin.dashboard'))

@admin_bp.route('/cancelar/<int:id_agendamento>', methods=['POST'])
def cancelar_ou_noshow(id_agendamento: int):
    """Remove o agendamento cancelado e ativa a fila cronológica de antecipação por horário."""

    agendamento = db.session.get(Agendamentos, id_agendamento)
    if not agendamento:
        return "Erro: Agendamento não encontrado.", 400

    data_cancelada = agendamento.data
    hora_cancelada = agendamento.hora
    barbeiro_cancelado = agendamento.barbeiro

    #Atualização da coluna status
    agendamento.status = 'cancelado'
    db.session.commit()

    print(f"\n⚠️ [DESMARCAÇÃO] Vaga aberta: Dia {data_cancelada} às {hora_cancelada}.")

    #Algoritmo Caça-Vagas
    candidatos = Agendamentos.query.filter(
        Agendamentos.hora == hora_cancelada,
        Agendamentos.barbeiro == barbeiro_cancelado,
        Agendamentos.status == 'ativo',
        Agendamentos.nome != None,
        Agendamentos.data > data_cancelada
    ).order_by(Agendamentos.data).all()

    if candidatos:
        cliente_alvo = candidatos[0]
        nome_barbeiro = "Bruno" if barbeiro_cancelado == "barbeiro_1" else "Matheus"

        print(f"\n🚀 [MOTOR CAÇA-VAGAS] Cliente prioritário detetado: {cliente_alvo.nome} (Agendado para dia {cliente_alvo.data} às {cliente_alvo.hora})")

        if cliente_alvo.canal == "whatsapp":
            print(
                f"Olá {cliente_alvo.nome}! 👋 Notícia fantástica da **BF Barbearia**! 💈\n\n"
                f"Uma vaga de última hora acabou de abrir para **dia {data_cancelada} às {hora_cancelada}** com o barbeiro {nome_barbeiro}.\n"
                f"Como tens corte marcado para o dia {cliente_alvo.data} às {cliente_alvo.hora}, gostarias de antecipar o teu atendimento?\n\n"
                f"🔥 Responde **SIM** para mudarmos o teu horário automaticamente."
            )
        else:
            print(
                f"BF Barbearia: {cliente_alvo.nome}, abriu vaga dia {agendamento.data} as {agendamento.hora} com {nome_barbeiro}. "
                f"Quer antecipar o seu corte de dia {cliente_alvo.data}? Responda SIM para trocar."
            )
    else:
        print("💡 [MOTOR CAÇA-VAGAS] Vaga livre no site público. Não existem clientes nos dias seguintes neste horário.")

    return redirect(url_for('admin.dashboard'))