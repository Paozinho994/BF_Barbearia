"""Constantes e regras de negócio da BF Barbearia."""

# Horários disponíveis para marcação (manhã e tarde)
HORARIOS = [
    "10:00", "10:30", "11:00", "11:30", "12:00", "12:30",
    "15:00", "15:30", "16:00", "16:30", "17:00", "17:30",
    "18:00", "18:30", "19:00", "19:30",
]

# Identificação interna -> nome público do profissional
BARBEIROS = {
    "barbeiro_1": "Bruno Ferreira",
    "barbeiro_2": "Matheus Santos",
    "qualquer": "Equipa BF",
}

BARBEIROS_INDIVIDUAIS = ("barbeiro_1", "barbeiro_2")

# Preços por serviço (valores em euros)
PRECOS_SERVICOS = {
    "corte+sobrancelha": 14.0,
    "corte+bigode+sobrancelha": 15.0,
    "corte+barba+sobrancelha": 19.0,
    "corte+barba": 18.0,
    "corte": 13.0,
    "corte zero+barba": 13.0,
    "corte M60": 10.0,
    "barba": 7.0,
}
PRECO_PADRAO = 15.0

# Estados possíveis de um agendamento
STATUS_ATIVO = "ativo"
STATUS_CANCELADO = "cancelado"
STATUS_EM_PROPOSTA = "em_proposta"
STATUS_RECUSADO_CICLO = "recusado_ciclo"

# Regras do Caça-Vagas
JANELA_SILENCIO = (22, 8)          # Convites congelados entre as 22h e as 08h
MARGEM_ANTECEDENCIA_MINUTOS = 30   # Vagas a menos de 30 min não disparam convites
TIMEOUT_CACA_VAGAS_MINUTOS = 30   # Tempo que o cliente tem para responder SIM/NÃO
CANAL_RECUSADO = "caça_vagas_recusado"

# Dias da semana em que a barbearia está fechada (weekday(): 0=Seg ... 6=Dom)
DIAS_FECHADOS = {0, 6}

# Nomes dos meses em português para o painel admin
MESES_PT = {
    1: "Janeiro", 2: "Fevereiro", 3: "Março", 4: "Abril",
    5: "Maio", 6: "Junho", 7: "Julho", 8: "Agosto",
    9: "Setembro", 10: "Outubro", 11: "Novembro", 12: "Dezembro",
}

# Formatos de data/hora usados em toda a aplicação
FORMATO_DATA = "%Y-%m-%d"
FORMATO_DATA_HORA = "%Y-%m-%d %H:%M"
FORMATO_HORA = "%H:%M"
