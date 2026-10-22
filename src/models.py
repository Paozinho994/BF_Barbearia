import secrets
from src import db
from datetime import datetime, timezone

class Agendamentos(db.Model):
    """Modelo que define a tabela de agendamentos no PostgreSQL"""
    __tablename__ = "agendamentos"

    #Chave Primária
    id = db.Column(db.Integer, primary_key=True)

    #Dados de Agendamento
    data = db.Column(db.String(10), nullable=False)
    hora = db.Column(db.String(5), nullable=False)
    barbeiro = db.Column(db.String(30), nullable=False)
    servico = db.Column(db.String(100), nullable=False)

    #Dados do Cliente
    nome = db.Column(db.String(100), nullable=True)
    telemovel = db.Column(db.String(20), nullable=True)
    canal = db.Column(db.String(20), default='nenhum')

    #Estado da Vaga
    status = db.Column(db.String(20), default='ativo', nullable=False)

    #Token aleatório único para links
    token_cancelamento = db.Column(
        db.String(40),
        unique=True,
        nullable=False,
        default=lambda: secrets.token_urlsafe(16)
    )

    #Timestamp de Criação
    criado_em = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    def __repr__(self) -> str:
        return f"<Agendamentos {self.id} - {self.nome} ({self.data} às {self.hora})>"

class HistoricoCacaVagas(db.Model):
    __tablename__ = "historico_caca_vagas"

    id = db.Column(db.Integer, primary_key=True)
    data_recuperacao = db.Column(db.String(10), nullable=False)
    nome_cliente = db.Column(db.String(100), nullable=False)
    barbeiro = db.Column(db.String(50), nullable=False)
    horario_recuperado = db.Column(db.String(50), nullable=False)
    valor = db.Column(db.Float, default=15.0)

    def __repr__(self):
        return f"<Historico {self.nome_cliente} - {self.data_recuperacao} - {self.valor}€>"
