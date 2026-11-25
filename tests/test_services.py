"""Testes unitários da lógica de serviços da BF Barbearia."""

from datetime import date, datetime, timedelta

import pytest

from src import db
from src.constants import (
    CANAL_RECUSADO,
    FORMATO_DATA,
    STATUS_ATIVO,
    STATUS_CANCELADO,
    STATUS_EM_PROPOSTA,
    STATUS_RECUSADO_CICLO,
)
from src.models import Agendamentos, HistoricoCacaVagas
from src.services import agendamentos, whatsapp


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def proxima_terca(dias: int = 7) -> str:
    """Data futura garantidamente aberta (terça-feira)."""
    d = date.today() + timedelta(days=dias)
    while d.weekday() != 1:
        d += timedelta(days=1)
    return d.strftime(FORMATO_DATA)


def dados_online(**overrides) -> dict:
    base = {
        "servico": "corte",
        "data": proxima_terca(),
        "barbeiro": "barbeiro_1",
        "hora": "10:00",
        "nome": "Teste Silva",
        "telemovel": "912345678",
        "canal": "whatsapp",
    }
    base.update(overrides)
    return base


def criar_agendamento_direto(**overrides) -> Agendamentos:
    """Insere um agendamento diretamente na BD, sem passar pelas regras."""
    base = {
        "data": proxima_terca(),
        "barbeiro": "barbeiro_1",
        "hora": "10:00",
        "nome": "Cliente Direto",
        "telemovel": "912345678",
        "servico": "corte",
        "canal": "whatsapp",
        "status": STATUS_ATIVO,
    }
    base.update(overrides)
    ag = Agendamentos(**base)
    db.session.add(ag)
    db.session.commit()
    return ag


# ---------------------------------------------------------------------------
# whatsapp.py — utilitários de contacto
# ---------------------------------------------------------------------------

class TestTelemovel:
    def test_normalizar_adiciona_prefixo_351(self):
        assert whatsapp.normalizar_telemovel("912 345 678") == "351912345678"

    def test_normalizar_mantem_prefixo_existente(self):
        assert whatsapp.normalizar_telemovel("351912345678") == "351912345678"

    def test_normalizar_vazio(self):
        assert whatsapp.normalizar_telemovel("") == ""
        assert whatsapp.normalizar_telemovel(None) == ""

    def test_valido_estrito_aceita_prefixos_pt(self):
        assert whatsapp.telemovel_valido("912345678", estrito=True)
        assert whatsapp.telemovel_valido("931234567", estrito=True)
        assert whatsapp.telemovel_valido("961234567", estrito=True)

    def test_valido_estrito_rejeita_outros_prefixos(self):
        # 98x não é um prefixo móvel português válido
        assert not whatsapp.telemovel_valido("984765432", estrito=True)
        assert not whatsapp.telemovel_valido("812345678", estrito=True)

    def test_valido_nao_estrito_aceita_98(self):
        # Modo não-estrito aceita qualquer número a começar por 9
        assert whatsapp.telemovel_valido("984765432")

    def test_valido_estrito_rejeita_comprimento_errado(self):
        assert not whatsapp.telemovel_valido("91234567", estrito=True)
        assert not whatsapp.telemovel_valido("9123456789", estrito=True)

    def test_valido_nao_estrito_aceita_qualquer_9(self):
        assert whatsapp.telemovel_valido("918765432")
        assert not whatsapp.telemovel_valido("123456789")

    def test_jid_whatsapp(self):
        assert whatsapp.jid_whatsapp("912345678") == "351912345678@s.whatsapp.net"


class TestFormatacao:
    def test_nome_barbeiro(self):
        assert whatsapp.nome_barbeiro("barbeiro_1") == "Bruno Ferreira"
        assert whatsapp.nome_barbeiro("desconhecido") == "Equipa BF"

    def test_formatar_servico(self):
        assert whatsapp.formatar_servico("corte+barba") == "CORTE + BARBA"
        assert whatsapp.formatar_servico("") == "SERVIÇO"
        assert whatsapp.formatar_servico(None) == "SERVIÇO"


# ---------------------------------------------------------------------------
# agendamentos.py — marcação online
# ---------------------------------------------------------------------------

class TestCriarAgendamentoOnline:
    def test_sucesso_cria_agendamento_ativo(self, app):
        with app.app_context():
            ag, erro = agendamentos.criar_agendamento_online(dados_online())
            assert erro is None
            assert ag.status == STATUS_ATIVO
            assert ag.barbeiro == "barbeiro_1"
            assert ag.token_cancelamento

    def test_rejeita_data_passada(self, app):
        with app.app_context():
            dados = dados_online(data="2020-01-01")
            ag, erro = agendamentos.criar_agendamento_online(dados)
            assert ag is None
            assert erro["status"] == 400
            assert "passados" in erro["mensagem"]

    def test_rejeita_telemovel_invalido(self, app):
        with app.app_context():
            ag, erro = agendamentos.criar_agendamento_online(dados_online(telemovel="123"))
            assert ag is None
            assert erro["status"] == 400
            assert "telemóvel" in erro["mensagem"]

    def test_rejeita_campos_em_falta(self, app):
        with app.app_context():
            ag, erro = agendamentos.criar_agendamento_online(dados_online(nome=""))
            assert ag is None
            assert erro["status"] == 400

    def test_rejeita_horario_ocupado(self, app):
        with app.app_context():
            criar_agendamento_direto()
            ag, erro = agendamentos.criar_agendamento_online(dados_online())
            assert ag is None
            assert erro["status"] == 400
            assert "preenchido" in erro["mensagem"]

    def test_rejeita_dia_fechado(self, app):
        with app.app_context():
            # Próximo domingo (fechado)
            d = date.today() + timedelta(days=7)
            while d.weekday() != 6:
                d += timedelta(days=1)
            ag, erro = agendamentos.criar_agendamento_online(
                dados_online(data=d.strftime(FORMATO_DATA))
            )
            assert ag is None
            assert erro["status"] == 400
            assert "fechada" in erro["mensagem"]

    def test_rejeita_data_invalida(self, app):
        with app.app_context():
            ag, erro = agendamentos.criar_agendamento_online(
                dados_online(data="data-qualquer")
            )
            assert ag is None
            assert erro["status"] == 400

    def test_qualquer_escolhe_barbeiro_livre(self, app):
        with app.app_context():
            criar_agendamento_direto(barbeiro="barbeiro_1", hora="10:00")
            ag, erro = agendamentos.criar_agendamento_online(
                dados_online(barbeiro="qualquer", hora="10:00")
            )
            assert erro is None
            assert ag.barbeiro == "barbeiro_2"

    def test_qualquer_rejeita_quando_lotado(self, app):
        with app.app_context():
            criar_agendamento_direto(barbeiro="barbeiro_1", hora="10:00")
            criar_agendamento_direto(barbeiro="barbeiro_2", hora="10:00",
                                     nome="Outro", telemovel="933333333")
            ag, erro = agendamentos.criar_agendamento_online(
                dados_online(barbeiro="qualquer", hora="10:00")
            )
            assert ag is None
            assert erro["status"] == 400


# ---------------------------------------------------------------------------
# agendamentos.py — disponibilidade
# ---------------------------------------------------------------------------

class TestHorariosLivres:
    def test_sem_params_devolve_todos(self, app):
        with app.app_context():
            assert len(agendamentos.horarios_livres("", "")) == len(
                agendamentos.HORARIOS
            )

    def test_remove_horarios_ocupados(self, app):
        with app.app_context():
            data = proxima_terca()
            criar_agendamento_direto(data=data, hora="10:00", barbeiro="barbeiro_1")
            livres = agendamentos.horarios_livres(data, "barbeiro_1")
            assert "10:00" not in livres
            assert "10:30" in livres

    def test_qualquer_so_remove_horas_cheias(self, app):
        with app.app_context():
            data = proxima_terca()
            criar_agendamento_direto(data=data, hora="10:00", barbeiro="barbeiro_1")
            livres = agendamentos.horarios_livres(data, "qualquer")
            assert "10:00" in livres  # barbeiro_2 ainda livre

    def test_data_passada_devolve_vazio(self, app):
        with app.app_context():
            assert agendamentos.horarios_livres("2020-01-01", "barbeiro_1") == []

    def test_dia_fechado_devolve_vazio(self, app):
        with app.app_context():
            # Próximo domingo (weekday 6 está em DIAS_FECHADOS)
            d = date.today() + timedelta(days=7)
            while d.weekday() != 6:
                d += timedelta(days=1)
            assert agendamentos.horarios_livres(d.strftime(FORMATO_DATA),
                                                "barbeiro_1") == []


# ---------------------------------------------------------------------------
# agendamentos.py — marcação manual
# ---------------------------------------------------------------------------

class TestCriarMarcacaoManual:
    def _dados(self, **overrides):
        base = {
            "nome": "Cliente Balcão",
            "telemovel": "912 345 678",
            "hora": "11:00",
            "data": proxima_terca(),
            "barbeiro": "barbeiro_1",
            "canal": "nenhum",
        }
        base.update(overrides)
        return base

    def test_sucesso_limpa_telemovel(self, app):
        with app.app_context():
            ag, erro = agendamentos.criar_marcacao_manual(self._dados())
            assert erro is None
            assert ag.telemovel == "912345678"
            assert ag.servico == agendamentos.SERVICO_MANUAL

    def test_rejeita_telemovel_invalido(self, app):
        with app.app_context():
            ag, erro = agendamentos.criar_marcacao_manual(self._dados(telemovel="123"))
            assert ag is None
            assert erro["status"] == 400

    def test_rejeita_horario_ocupado(self, app):
        with app.app_context():
            criar_agendamento_direto(hora="11:00", barbeiro="barbeiro_1")
            ag, erro = agendamentos.criar_marcacao_manual(self._dados())
            assert ag is None
            assert erro["status"] == 400


# ---------------------------------------------------------------------------
# agendamentos.py — self-service (cancelar / reagendar)
# ---------------------------------------------------------------------------

class TestCancelarPublico:
    def test_token_inexistente(self, app):
        with app.app_context():
            ag, erro = agendamentos.cancelar_agendamento_publico("token-falso")
            assert ag is None
            assert erro["status"] == 404

    def test_cancelamento_liberta_vaga(self, app):
        with app.app_context():
            ag = criar_agendamento_direto()
            token = ag.token_cancelamento
            ag, erro = agendamentos.cancelar_agendamento_publico(token)
            assert erro is None
            db.session.refresh(ag)
            assert ag.status == STATUS_CANCELADO

    def test_nao_encontra_ja_cancelado(self, app):
        with app.app_context():
            ag = criar_agendamento_direto(status=STATUS_CANCELADO)
            _, erro = agendamentos.cancelar_agendamento_publico(ag.token_cancelamento)
            assert erro["status"] == 404


class TestReagendar:
    def test_sucesso_atualiza_campos(self, app):
        with app.app_context():
            ag = criar_agendamento_direto()
            token = ag.token_cancelamento
            nova_data = proxima_terca(14)
            ag, erro = agendamentos.reagendar_agendamento(token, {
                "data": nova_data, "hora": "15:00", "barbeiro": "barbeiro_2",
            })
            assert erro is None
            assert ag.data == nova_data
            assert ag.hora == "15:00"
            assert ag.barbeiro == "barbeiro_2"
            # Dados do cliente mantêm-se
            assert ag.nome == "Cliente Direto"

    def test_token_inexistente(self, app):
        with app.app_context():
            ag, erro = agendamentos.reagendar_agendamento("falso", {
                "data": proxima_terca(), "hora": "15:00", "barbeiro": "barbeiro_1",
            })
            assert ag is None
            assert erro["status"] == 404

    def test_rejeita_data_passada(self, app):
        with app.app_context():
            ag = criar_agendamento_direto()
            _, erro = agendamentos.reagendar_agendamento(ag.token_cancelamento, {
                "data": "2020-01-01", "hora": "15:00", "barbeiro": "barbeiro_1",
            })
            assert erro["status"] == 400

    def test_rejeita_horario_ocupado_por_outro(self, app):
        with app.app_context():
            ag = criar_agendamento_direto()
            criar_agendamento_direto(hora="15:00", barbeiro="barbeiro_2",
                                     nome="Ocupante", telemovel="933333333")
            _, erro = agendamentos.reagendar_agendamento(ag.token_cancelamento, {
                "data": ag.data, "hora": "15:00", "barbeiro": "barbeiro_2",
            })
            assert erro["status"] == 400

    def test_permite_manter_mesmo_horario(self, app):
        """Reagendar para o próprio slot não deve contar como ocupado."""
        with app.app_context():
            ag = criar_agendamento_direto()
            ag, erro = agendamentos.reagendar_agendamento(ag.token_cancelamento, {
                "data": ag.data, "hora": ag.hora, "barbeiro": ag.barbeiro,
            })
            assert erro is None

    def test_rejeita_reagendar_para_dia_fechado(self, app):
        with app.app_context():
            ag = criar_agendamento_direto()
            d = date.today() + timedelta(days=7)
            while d.weekday() != 6:
                d += timedelta(days=1)
            _, erro = agendamentos.reagendar_agendamento(ag.token_cancelamento, {
                "data": d.strftime(FORMATO_DATA), "hora": "15:00",
                "barbeiro": "barbeiro_1",
            })
            assert erro["status"] == 400
            assert "fechada" in erro["mensagem"]


# ---------------------------------------------------------------------------
# agendamentos.py — motor Caça-Vagas
# ---------------------------------------------------------------------------

class TestCacaVagas:
    def test_agendamento_inexistente_devolve_false(self, app):
        with app.app_context():
            assert agendamentos.executar_algoritmo_caca_vagas(99999) is False

    def test_cancelamento_sem_candidatos_apenas_liberta(self, app):
        with app.app_context():
            ag = criar_agendamento_direto()
            assert agendamentos.executar_algoritmo_caca_vagas(ag.id) is True
            db.session.refresh(ag)
            assert ag.status == STATUS_CANCELADO

    def test_propoe_proximo_cliente_da_fila(self, app):
        with app.app_context():
            cancelado = criar_agendamento_direto(hora="10:00", barbeiro="barbeiro_1")
            proximo = criar_agendamento_direto(
                data=proxima_terca(14), hora="10:00", barbeiro="barbeiro_1",
                nome="Na Fila", telemovel="944444444",
            )
            agendamentos.executar_algoritmo_caca_vagas(cancelado.id)
            db.session.refresh(proximo)
            # O próximo cliente fica em proposta (ou já resolvido pelo timeout)
            assert proximo.status in (STATUS_EM_PROPOSTA, STATUS_ATIVO,
                                      STATUS_RECUSADO_CICLO)

    def test_nao_propoe_cliente_com_mesmo_dia(self, app):
        with app.app_context():
            cancelado = criar_agendamento_direto(hora="10:00", barbeiro="barbeiro_1")
            mesmo_dia = criar_agendamento_direto(
                data=cancelado.data, hora="10:00", barbeiro="barbeiro_1",
                nome="Mesmo Dia", telemovel="955555555",
            )
            agendamentos.executar_algoritmo_caca_vagas(cancelado.id)
            db.session.refresh(mesmo_dia)
            assert mesmo_dia.status == STATUS_ATIVO


class TestWebhookCancaVagas:
    def _payload(self, texto: str, telemovel: str = "912345678") -> dict:
        return {
            "data": {
                "message": {"conversation": texto},
                "key": {"remoteJid": f"351{telemovel}@s.whatsapp.net"},
            }
        }

    def test_extrai_texto_e_telemovel(self):
        payload = self._payload("SIM")
        assert agendamentos._extrair_texto_mensagem(payload) == "SIM"
        assert agendamentos._extrair_telemovel_remetente(payload) == "912345678"

    def test_mensagem_sem_sim_nem_nao_e_ignorada(self, app):
        with app.app_context():
            payload, status = agendamentos.processar_resposta_canca_vagas(
                self._payload("OLÁ")
            )
            assert status == 200
            assert payload["status"] == "ignorado"

    def test_sem_cliente_em_proposta_devolve_404(self, app):
        with app.app_context():
            payload, status = agendamentos.processar_resposta_canca_vagas(
                self._payload("SIM")
            )
            assert status == 404

    def test_recusa_reativa_cliente_e_marca_canal(self, app):
        with app.app_context():
            cliente = criar_agendamento_direto(
                status=STATUS_EM_PROPOSTA, telemovel="912345678",
            )
            payload, status = agendamentos.processar_resposta_canca_vagas(
                self._payload("NÃO")
            )
            assert status == 200
            db.session.refresh(cliente)
            assert cliente.status == STATUS_ATIVO
            assert cliente.canal == CANAL_RECUSADO

    def test_confirmacao_troca_vaga_e_regista_historico(self, app):
        with app.app_context():
            # Vaga cancelada mais cedo, mesmo barbeiro/hora
            vaga = criar_agendamento_direto(
                data=proxima_terca(7), hora="10:00", barbeiro="barbeiro_1",
                status=STATUS_CANCELADO, nome=None, telemovel=None,
            )
            cliente = criar_agendamento_direto(
                data=proxima_terca(14), hora="10:00", barbeiro="barbeiro_1",
                status=STATUS_EM_PROPOSTA, nome="Aceitou", telemovel="912345678",
            )
            payload, status = agendamentos.processar_resposta_canca_vagas(
                self._payload("SIM")
            )
            assert status == 200
            db.session.refresh(vaga)
            db.session.refresh(cliente)
            assert vaga.status == STATUS_ATIVO
            assert vaga.nome == "Aceitou"
            assert cliente.status == STATUS_CANCELADO
            assert HistoricoCacaVagas.query.count() == 1


class TestTimeoutCacaVagas:
    def test_cliente_em_proposta_vira_recusado(self, app):
        with app.app_context():
            # Tal como em produção: o timeout recebe o ID da vaga cancelada real
            vaga = criar_agendamento_direto(
                data=proxima_terca(7), status=STATUS_CANCELADO,
                nome=None, telemovel=None,
            )
            cliente = criar_agendamento_direto(
                data=proxima_terca(14), hora="10:00", barbeiro="barbeiro_1",
                status=STATUS_EM_PROPOSTA,
            )
            agendamentos.verificar_timeout_caca_vagas(cliente.id, vaga.id, app)
            db.session.refresh(cliente)
            assert cliente.status == STATUS_RECUSADO_CICLO

    def test_cliente_ativo_nao_e_afetado(self, app):
        with app.app_context():
            cliente = criar_agendamento_direto(status=STATUS_ATIVO)
            agendamentos.verificar_timeout_caca_vagas(cliente.id, 0, app)
            db.session.refresh(cliente)
            assert cliente.status == STATUS_ATIVO

    def test_cliente_inexistente_nao_falha(self, app):
        with app.app_context():
            agendamentos.verificar_timeout_caca_vagas(99999, 0, app)  # não deve levantar


# ---------------------------------------------------------------------------
# agendamentos.py — utilitários diversos
# ---------------------------------------------------------------------------

class TestUtilitarios:
    def test_preco_exato(self):
        assert agendamentos.preco_do_servico("corte") == 13.0
        assert agendamentos.preco_do_servico("barba") == 7.0

    def test_preco_case_insensitive(self):
        assert agendamentos.preco_do_servico("CORTE") == 13.0

    def test_preco_desconhecido_usa_padrao(self):
        assert agendamentos.preco_do_servico("servico_inexistente") == 15.0
        assert agendamentos.preco_do_servico("") == 15.0
        assert agendamentos.preco_do_servico(None) == 15.0

    def test_buscar_por_token(self, app):
        with app.app_context():
            ag = criar_agendamento_direto()
            assert agendamentos.buscar_por_token_cancelamento(
                ag.token_cancelamento
            ).id == ag.id
            assert agendamentos.buscar_por_token_cancelamento("xxx") is None

    def test_montar_relatorio_vazio(self, app):
        with app.app_context():
            rel = agendamentos.montar_relatorio()
            assert rel["total_antecipacoes"] == 0
            assert rel["total_faturado"] == 0

    def test_montar_contexto_dashboard(self, app):
        with app.app_context():
            data = proxima_terca()
            criar_agendamento_direto(data=data)
            ctx = agendamentos.montar_contexto_dashboard(data, "")
            assert ctx["total_hoje"] == 1
            assert len(ctx["agendamentos"]) == 1


# ---------------------------------------------------------------------------
# Rotas públicas (cliente)
# ---------------------------------------------------------------------------

class TestRotasCliente:
    def test_index_renderiza_formulario(self, client):
        resp = client.get("/")
        assert resp.status_code == 200
        assert b"Agendamento" in resp.data

    def test_agendar_com_erro_renderiza_template(self, client):
        resp = client.post("/agendar", data={
            "servico": "corte", "data": "2020-01-01", "barbeiro": "barbeiro_1",
            "hora": "10:00", "nome": "X", "telemovel": "912345678",
            "canal": "whatsapp",
        })
        assert resp.status_code == 400
        assert b"passados" in resp.data

    def test_gestao_agendamento_get(self, client, app):
        with app.app_context():
            ag = criar_agendamento_direto()
            token = ag.token_cancelamento
        resp = client.get(f"/cancelar_vaga/{token}")
        assert resp.status_code == 200
        assert b"Reagendar" in resp.data
        assert b"Cancelar" in resp.data

    def test_gestao_token_invalido_404(self, client):
        assert client.get("/cancelar_vaga/token-inexistente").status_code == 404

    def test_gestao_cancelar_post(self, client, app):
        with app.app_context():
            ag = criar_agendamento_direto()
            token = ag.token_cancelamento
        resp = client.post(f"/cancelar_vaga/{token}", data={"acao": "cancelar"})
        assert resp.status_code == 200
        assert b"Cancelado" in resp.data

    def test_gestao_reagendar_post(self, client, app):
        with app.app_context():
            ag = criar_agendamento_direto()
            token = ag.token_cancelamento
        resp = client.post(f"/cancelar_vaga/{token}", data={
            "acao": "reagendar",
            "data": proxima_terca(14),
            "hora": "15:00",
            "barbeiro": "barbeiro_2",
        })
        assert resp.status_code == 302  # redirect para a página de gestão

    def test_verificar_disponibilidade(self, client, app):
        with app.app_context():
            data = proxima_terca()
        resp = client.get(f"/verificar-disponibilidade?data={data}&barbeiro=barbeiro_1")
        assert resp.status_code == 200
        assert isinstance(resp.get_json(), list)
