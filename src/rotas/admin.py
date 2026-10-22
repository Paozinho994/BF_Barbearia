import re
import requests
from flask import session, Blueprint, render_template, request, redirect, url_for
from datetime import datetime
import os
from src import db
from src.models import Agendamentos

# Inicializa o Blueprint do administrador
admin_bp = Blueprint('admin', __name__)

# 🔒 SENTINELA DE SEGURANÇA: Protege todas as rotas do Blueprint /admin
@admin_bp.before_request
def verificar_autenticacao():
    if request.endpoint == 'admin.login':
        return

    # Caso a chave 'admin_logado' não estiver na sessão do browser, expulsa para o login
    if not session.get('admin_logado'):
        return redirect(url_for('admin.login'))

# 🔑 ROTA DA TELA DE LOGIN & PROCESSAMENTO
@admin_bp.route('/login', methods=['GET', 'POST'])
def login():
    erro = None
    if request.method == 'POST':
        utilizador_submetido = request.form.get('utilizador', '').strip()
        senha_submetida = request.form.get('senha', '')

        #Leitura do .env
        admin = os.getenv("ADMIN_USER", "chave_local")
        admin_password = os.getenv("SENHA", "chave_local")

        #Validação das credenciais de acesso
        if utilizador_submetido == admin and senha_submetida == admin_password:
            session['admin_logado'] = True
            return redirect(url_for('admin.dashboard'))
        else:
            erro = "Utilizador ou Password incorretos!"
    return render_template("admin/login.html", erro=erro)

# 🚪 ROTA DE LOGOUT (SAIR COM SEGURANÇA)
@admin_bp.route('/logout')
def logout():
    session.pop('admin_logado', None) #Destrói a tranca da sessão
    return redirect(url_for('admin.login'))

@admin_bp.route('/')
def dashboard() -> str:
    """Renderiza o painel de administração principal"""
    from src.constants import HORARIOS

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
        data_hoje=data_exibicao_formatada,
        data_hoje_crua=data_selecionada_crua,
        data_atual_sistema=data_hoje_crua
    )

@admin_bp.route('/marcar', methods=['POST'])
def criar_marcacao_manual():
    """Recebe e processa os dados do formulário de marcação manual."""
    from src.rotas.cliente import disparar_notificacao_inteligente

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
        "id": nova_marcacao.id, "data": data_escolhida, "barbeiro": barbeiro_escolhido, "hora": hora_corte,
        "nome": nome_cliente, "telemovel": telemovel, "servico": "Marcação Manual (Telefone)", "canal": canal_notificacao
    }
    disparar_notificacao_inteligente(dados_notificacao, origem="MANUAL/BALCÃO")

    return redirect(url_for('admin.dashboard'))

def executar_algoritmo_caca_vagas(id_agendamento: int, id_cliente_ignorar: int = None):
    """Motor Centralizado do Caça-Vagas da BF Barbearia."""
    from datetime import datetime, timedelta
    from src import scheduler

    #Se o agendamento não existir ou já tiver sido preenchido, reset da fila
    agendamento = db.session.get(Agendamentos, id_agendamento)
    if not agendamento or agendamento.status != 'ativo':
        print(f"⚠️ [MOTOR CENTRAL] Agendamento {id_agendamento} já não está ativo. A verificar fila de espera...")
        if not agendamento:
            Agendamentos.query.filter_by(status='recusado_ciclo').update({Agendamentos.status: 'ativo'})
            db.session.commit()
            return False

    data_cancelada = agendamento.data
    hora_cancelada = agendamento.hora
    barbeiro_cancelado = agendamento.barbeiro

    #Tranca de Silêncio Noturno (Entre as 22h00 e as 07h59)
    agora = datetime.now()
    if agora.hour >= 22 or agora.hour < 8:
        if agendamento.status == 'ativo':
            agendamento.status = 'cancelado'
            db.session.commit()
        print(f"[JANELA INTELIGENTE] 🔕 Silêncio Noturno ({agora.strftime('%H:%M')}). Vaga libertada, mas convites congelados.")
        return True

    #Tranca de Margem de Antecedência mínima (30 Minutos)
    if data_cancelada == agora.strftime('%Y-%m-%d'):
        try:
            hora_vaga_obj = datetime.strptime(f"{data_cancelada} {hora_cancelada}", "%Y-%m-%d %H:%M")
            if hora_vaga_obj - agora < timedelta(minutes=30):
                if agendamento.status == 'ativo':
                    agendamento.status = 'cancelado'
                    db.session.commit()
                print(f"[JANELA INTELIGENTE] ⏱️ Vaga das {hora_cancelada} está muito em cima da hora. Convites abortados.")
                return True
        except ValueError:
            pass

    #Libertar o horário mudando para 'cancelado'
    if agendamento.status == 'ativo':
        agendamento.status = 'cancelado'
        db.session.commit()

    #Executar a pesquisa de clientes no futuro
    candidatos = Agendamentos.query.filter(
        Agendamentos.hora == hora_cancelada,
        Agendamentos.barbeiro == barbeiro_cancelado,
        Agendamentos.status == 'ativo',
        Agendamentos.nome != None,
        Agendamentos.data > data_cancelada,
        Agendamentos.canal != 'caça_vagas_recusado'
    ).order_by(Agendamentos.data).all()

    if candidatos:
        cliente_alvo = candidatos[0]
        nome_barbeiro = "Bruno Ferreira" if barbeiro_cancelado == "barbeiro_1" else "Matheus Santos"

        print(f"🚀 [MOTOR CENTRAL] Cliente prioritário detetado: {cliente_alvo.nome}")

        telemovel_limpo = re.sub(r'\D', '', cliente_alvo.telemovel)
        telemovel_api = f"351{telemovel_limpo}" if len(telemovel_limpo) == 9 else telemovel_limpo

        #Tranca o cliente atual como proposta
        cliente_alvo.status = 'em_proposta'
        db.session.commit()

        if cliente_alvo.canal == "whatsapp" or cliente_alvo.canal == "nenhum":
        # Monta o texto do convite
            texto_convite_whatsapp = (
                f"Olá {cliente_alvo.nome}! 👋 Notícia fantástica da **BF Barbearia**! 💈\n\n"
                f"Uma vaga de última hora acabou de abrir para **dia {data_cancelada} às {hora_cancelada}** com o profissional {nome_barbeiro}.\n\n"
                f"Como tens corte marcado para o dia {cliente_alvo.data} às {cliente_alvo.hora}, gostarias de antecipar o teu atendimento?\n\n"
                f"⏳ *Nota:* Tens **30 minutos** para responder antes que a vaga passe para o próximo cliente.\n\n"
                f"🔥 Responde **SIM** para aceitar a troca automática ou **NÃO** para passar a oportunidade."
            )

            # Disparo real via a tua Evolution API local ativa
            import os
            API_BASE = os.getenv("EVOLUTION_API_URL", "https://obtuse-pasty-traitor.ngrok-free.dev")
            API_KEY_EVOLUTION = os.getenv("FLASK_SECRET_KEY", "chave_local")
            URL_EVOLUTION = f"{API_BASE}/message/sendText/BF-Barbearia"
            payload = {
                "number": telemovel_api,
                "options": {
                    "delay": 3000,
                    "presence": "composing"
                },
                "text": texto_convite_whatsapp
            }
            headers = {"apikey": API_KEY_EVOLUTION, "Content-Type": "application/json"}

            try:
                resposta = requests.post(URL_EVOLUTION, json=payload, headers=headers, timeout=8)
                if resposta.status_code in [200, 201]:
                    print(f"🚀 [CAÇA-VAGAS WHATSAPP] Convite do Caça-Vagas entregue a {cliente_alvo.nome}")
            except Exception as e:
                print(f"❌ [ERRO REDE WHATSAPP] Falha ao comunicar com a Evolution API: {e}")

        import pytz
        from datetime import datetime, timedelta
        from flask import current_app

        #Temporizador
        tz = pytz.timezone("Europe/Lisbon")
        tempo_limite = datetime.now(tz) + timedelta(minutes=30)
        app_real = current_app._get_current_object()

        from src import scheduler

        scheduler.add_job(
            verificar_timeout_caca_vagas,
            trigger='date',
            run_date=tempo_limite,
            args=[cliente_alvo.id, data_cancelada, hora_cancelada, barbeiro_cancelado, id_agendamento, app_real],
            id=f"timeout_caca_vagas_{cliente_alvo.id}",
            replace_existing=True
        )
        print(f"⏱️ [CAÇA-VAGAS] Temporizador de 30 minutos ativado para {cliente_alvo.nome} (ID: {cliente_alvo.id}).")

    else:
        print("💡 [MOTOR CENTRAL] Sem clientes em fila de espera para este horário. Vaga aberta no site.")
        Agendamentos.query.filter_by(status='recusado_ciclo').update({Agendamentos.status: 'ativo'})
        db.session.commit()
    return True

def verificar_timeout_caca_vagas(id_cliente: int, data_vaga: str, hora_vaga: str, barbeiro_vaga: str, id_vaga_cancelada: int, app_instancia: any):
    """Função de retaguarda que roda se o cliente ignorar o convite por 30 minutos."""
    from src import db
    from src.models import Agendamentos

    with app_instancia.app_context():
        cliente = db.session.get(Agendamentos, id_cliente)

        #Se o cliente ainda estiver "em_proposta", significa que o tempo terminou e não respondeu
        if cliente and cliente.status == 'em_proposta':
            print(f"⏳ [TIMEOUT 30 MIN] O cliente {cliente.nome} não respondeu. A libertar vaga...")

            #Alteramos para 'recusado_ciclo' para o motor saltar apenas neste ciclo
            cliente.status = 'recusado_ciclo'
            db.session.commit()

            #⏳ Alerta de cortesia de 30 minutos esgotados
            try:
                import os
                import requests
                import re

                API_BASE = os.getenv("EVOLUTION_API_URL", "https://obtuse-pasty-traitor.ngrok-free.dev")
                API_KEY_EVOLUTION = os.getenv("FLASK_SECRET_KEY", "chave_local")
                URL_EVOLUTION = f"{API_BASE}/message/sendText/BF-Barbearia"

                telemovel_limpo = re.sub(r'\D', '', cliente.telemovel)
                telemovel_api = f"351{telemovel_limpo}" if len(telemovel_limpo) == 9 else telemovel_limpo

                texto_timeout = (
                    f"Olá, {cliente.nome}! ⏳\n\n"
                    f"O limite de **30 minutos** para uma resposta terminou."
                    f"Mas não te preocupes. O teu corte continua **100% confirmado para o dia {cliente.data} às {cliente.hora}**. Até breve! 💈"
                )

                payload = {
                    "number": telemovel_api,
                    "options": {
                        "delay": 1500,
                        "presence": "composing"
                    },
                    "text": texto_timeout
                }
                headers = {"apikey": API_KEY_EVOLUTION, "Content-Type": "application/json"}

                requests.post(URL_EVOLUTION, json=payload, headers=headers, timeout=5)
                print(f"⏱️ [TIMEOUT] Notificação de tempo limite enviada com sucesso para {cliente.nome}.")
            except Exception as e_msg:
                print(f"⚠️ [TIMEOUT] Falha ao enviar mensagem de tempo esgotado: {e_msg}")

            #Passa em cascata para o próximo candidato da lista
            print(f"⏭️ [TIMEOUT] A saltar para o próximo candidato da fila...")
            #Ajuste do motor passando ao id original de agendamento
            executar_algoritmo_caca_vagas(id_agendamento=id_vaga_cancelada)

        else:
            print(f"✅ [TIMEOUT] Verificação concluída: O cliente {cliente.nome if cliente else id_cliente} respondeu a tempo ou foi modificado.")

@admin_bp.route('/cancelar/<int:id_agendamento>', methods=['POST'])
def cancelar_ou_noshow(id_agendamento: int):
    """Rota do Painel de Controlo que aciona o Motor do Caça-Vagas."""

    sucesso = executar_algoritmo_caca_vagas(id_agendamento)
    if not sucesso:
        return "Erro: Agendamento não encontrado ou já cancelado.", 400
    return redirect(url_for('admin.dashboard'))

#ROTINA MATINAL DE LEMBRETES (APScheduler)

def lembretes_matinais():
    """Rotina executada às 08:00h para notificar os clientes do dia."""
    import os
    import time
    from datetime import date
    import requests
    import re
    import random
    from src import db
    from src.models import Agendamentos

    hoje_str = date.today().isoformat()
    print(f"[LEMBRETES] A iniciar varredura para o dia: {hoje_str}")

    EVOLUTION_API_URL = os.getenv("EVOLUTION_API_URL", "https://obtuse-pasty-traitor.ngrok-free.dev")
    EVOLUTION_KEY = os.getenv("FLASK_SECRET_KEY", "chave_local")

    url_envio = f"{EVOLUTION_API_URL}/message/sendText/BF-Barbearia"
    headers = {"Content-Type": "application/json", "apikey": EVOLUTION_KEY}

    try:
        print("[LEMBRETES] RECONSTRUÇÃO: A limpar trancas antigas do Caça-Vagas...")
        Agendamentos.query.filter(
            Agendamentos.status.in_(['recusado_ciclo', 'em_proposta'])
        ).update({Agendamentos.status: 'ativo'}, synchronize_session=False)
        db.session.commit()
        print("[LEMBRETES] ✨ Manutenção concluída. Base de dados pronta para o novo dia!")

        #Filtragem pela data e status
        agendamentos_hoje = Agendamentos.query.filter_by(
            data=hoje_str,
            status='ativo'
        ).all()

        if not agendamentos_hoje:
            print("[LEMBRETES] Nenhum agendamento ativo encontrado para hoje.")
            return

        total = len(agendamentos_hoje)
        print(f"[LEMBRETES] Encontrados {total} lembretes para enviar.")

        #Loop de disparos de lembretes
        for indice, agendamento in enumerate(agendamentos_hoje, start=1):
            cliente_nome = agendamento.nome if agendamento.nome else "Cliente"
            #Validação: ignora caso cliente não tenha telemóvel registado
            try:
                if not agendamento.telemovel:
                    print(f"[LEMBRETES] ⚠️ [{indice}/{total}] Ignorado: {cliente_nome} não tem telemóvel registado.")
                    continue

                telemovel_limpo = re.sub(r'\D', '', agendamento.telemovel)

                if not telemovel_limpo.startswith('351') and len(telemovel_limpo) == 9:
                    telemovel_limpo = f"351{telemovel_limpo}"

                saudacoes = ["Olá,", "Viva,", "Boas,", "Como estás,"]
                lembretes = [f"Passamos para lembrar que o teu corte está agendado para", f"Vimos recordar-te que o teu corte está agendado para", f"Informamos que o teu corte está agendado para"]
                despedida = ["Até já! ✂️", "Contamos contigo! 💈", "Abraço de toda a equipe!"]

                texto_lembrete = f"{random.choice(saudacoes)} {agendamento.nome}! {random.choice(lembretes)} hoje, às {agendamento.hora}. {random.choice(despedida)}"

                headers = {
                    "Content-Type": "application/json", "apikey": EVOLUTION_KEY}

                payload = {
                    "number": telemovel_limpo,
                    "options": {
                        "delay": 1500,
                        "presence": "composing"
                    },
                    "text": texto_lembrete
                }

                resposta = requests.post(url_envio, json=payload, headers=headers, timeout=10)

                if resposta.status_code in [200, 201]:
                    print(f"[LEMBRETES] ✅ [{indice}/{total}] Enviado com sucesso para {agendamento.nome}.")
                else:
                    print(f"[LEMBRETES] ⚠️ Erro no envio para {agendamento.nome}: Status {resposta.status_code}")

            except requests.exceptions.RequestException as e_api:
                # Captura falhas de rede específicas do requests (ex: Ngrok offline)
                print(f"[LEMBRETES] ❌ [{indice}/{total}] Falha de conexão ao enviar para {cliente_nome}: {str(e_api)}")
            except Exception as erro_envio:
                print(f"[LEMBRETES] 💥 Falha de rede ao contactar a Evolution API: {erro_envio}")

            #Delay de 2 segundos entre mensagens
            if indice < total:
                tempo_espera = random.randint(2, 10)
                time.sleep(tempo_espera)

    except Exception as e:
        print(f"[LEMBRETES] Erro geral ao processar base de dados: {e}")

@admin_bp.route('/relatorio')
def ver_relatorio():
    from src.models import HistoricoCacaVagas
    from src import db

    #Encontra todas as antecipações bem sucedidas gravadas pelo Caça-Vagas
    historico = HistoricoCacaVagas.query.order_by(HistoricoCacaVagas.id.desc()).all()

    #Calcula as métricas totais em tempo real
    total_antecipacoes = len(historico)
    total_faturado_recuperado = sum(registo.valor for registo in historico)

    #Retorna os dados numa página simples
    return f"""
    <html>
    <head>
        <title>Auditoria de Ganhos</title>
        <style>
            body {{ font-family: sans-serif; background: #0a0a0a; color: #fff; padding: 40px; }}
            .card {{ background: #171717; border: 1px solid #262626; padding: 20px; border-radius: 8px; max-width: 600px; margin-bottom: 20px; }}
            table {{ width: 100%; border-collapse: collapse; margin-top: 20px; }}
            th, td {{ padding: 10px; text-align: left; border-bottom: 1px solid #262626; font-size: 0.875rem; }}
            th {{ color: #eab308; }}
        </style>
    </head>
    <body>
        <h2>📊 Relatório Mensal de Faturação Recuperada</h2>
        <div class="card">
            <p>🔄 Total de Vagas Salvas pelo Caça-Vagas: <strong>{total_antecipacoes}</strong></p>
            <p>💰 Total de Faturação Recuperada: <strong style="color: #4ade80; font-size: 1.25rem;">{total_faturado_recuperado:.2f}€</strong></p>
        </div>

        <h3>📋 Histórico Detalhado de Antecipações:</h3>
        <table>
            <tr>
                <th>Data</th>
                <th>Cliente</th>
                <th>Barbeiro</th>
                <th>Hora Vaga</th>
                <th>Valor Ganho</th>
            </tr>
            {"".join(f"<tr><td>{r.data_recuperacao}</td><td>{r.nome_cliente}</td><td>{'Bruno' if r.barbeiro == 'barbeiro_1' else 'Matheus'}</td><td>{r.horario_recuperado}</td><td style='color:#4ade80;'>{r.valor:.2f}€</td></tr>" for r in historico)}
        </table>
        <br><a href="/admin/" style="color: #a3a3a3; text-decoration: none; font-size: 0.813rem;">← Voltar ao Painel</a>
    </body>
    </html>
    """