import os
from src import create_app, db

# Inicializa a factory do Flask carregando os teus modelos do models.py
app = create_app()

with app.app_context():
    print("⏳ A conectar ao PostgreSQL remoto do Render...")
    print("🛠️ A desenhar a tabela de agendamentos...")

    # Este comando cria fisicamente todas as tabelas mapeadas no teu models.py na nuvem
    db.create_all()

    print("✅ SUCESSO: Tabelas criadas com sucesso no PostgreSQL do Render!")
