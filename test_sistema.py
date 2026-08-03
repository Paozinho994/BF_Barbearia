import pytest
from src import create_app, db
from src.models import Agendamentos


@pytest.fixture
def client():
    """Configura um ambiente de teste isolado e força o fecho das conexões"""
    app = create_app()
    app.config['TESTING'] = True
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'

    with app.test_client() as client:
        with app.app_context():
            db.create_all()
            yield client
            # CORREÇÃO: Limpa a sessão explicitamente antes de apagar as tabelas
            db.session.remove()
            db.drop_all()


def test_fluxo_completo_agendamento_e_admin(client):
    """TESTE AUTOMÁTICO 1: Verifica caminhos, cruzamento de rotas e gravação"""
    resposta_index = client.get('/')
    assert resposta_index.status_code == 200

    dados_agendamento = {
        'servico': 'corte+barba',
        'data': '2026-08-10',
        'barbeiro': 'barbeiro_1',
        'hora': '11:00',
        'nome': 'Cliente Teste Automatico',
        'telemovel': '911111111',
        'canal': 'whatsapp'
    }
    resposta_agendar = client.post('/agendar', data=dados_agendamento)
    assert resposta_agendar.status_code == 200

    resposta_vagas = client.get('/verificar-disponibilidade?data=2026-08-10&barbeiro=barbeiro_1')
    horarios_livres = resposta_vagas.get_json()
    assert '11:00' not in horarios_livres

    resposta_admin = client.get('/admin/?data=2026-08-10')
    assert resposta_admin.status_code == 200
    assert b'Cliente Teste Automatico' in resposta_admin.data


def test_bloqueio_de_colisao_dupla(client):
    """TESTE AUTOMÁTICO 2: Garante que o sistema impede duas marcações na mesma hora"""
    dados = {
        'servico': 'corte', 'data': '2026-08-10', 'barbeiro': 'barbeiro_1',
        'hora': '14:00', 'nome': 'Manuel Silva', 'telemovel': '922222222'
    }
    res1 = client.post('/agendar', data=dados)
    assert res1.status_code == 200

    dados_clone = dados.copy()
    dados_clone['nome'] = 'Rodrigo Santos'
    res2 = client.post('/agendar', data=dados_clone)

    assert res2.status_code == 400


def test_rejeicao_de_telemovel_invalido(client):
    """TESTE AUTOMÁTICO 3: Garante que o backend bloqueia números com tamanho errado"""
    dados_errados = {
        'servico': 'corte', 'data': '2026-08-10', 'barbeiro': 'barbeiro_1',
        'hora': '16:00', 'nome': 'Manuel Errado',
        'telemovel': '91234',  # Apenas 5 dígitos (Tem de falhar)
        'canal': 'whatsapp'
    }
    resposta = client.post('/agendar', data=dados_errados)

    # O sistema TEM de devolver o erro 400 e recusar a gravação no PostgreSQL
    assert resposta.status_code == 400

