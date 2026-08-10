# 💈 BF Barbearia - Sistema de Agendamento Inteligente & Caça-Vagas Automático

> 🌐 **Aceda à aplicação em produção:** [https://bf-barbearia.onrender.com/](https://bf-barbearia.onrender.com/)

Este é o ecossistema digital da **BF Barbearia**, desenvolvido para automatizar o fluxo de marcações de clientes, combater *no-shows* (faltas comparência) e otimizar a agenda dos profissionais através de um algoritmo reativo de antecipação alimentado por APIs de mensagens instantâneas (WhatsApp/SMS).

---

## 🚀 Funcionalidades Principais

*   **Calendário Inteligente Anti-erros**: Bloqueio reativo de datas no passado e ocultação automática de horários que já passaram no próprio dia.
*   **Gestão Dinâmica de Folgas**: Fecho automatizado do sistema aos Domingos e Segundas-Feiras com avisos em tempo real na interface do utilizador.
*   **Distribuição Justa de Vagas**: Algoritmo de balanceamento de carga de trabalho entre barbeiros quando o cliente seleciona a opção "Qualquer Profissional".
*   **Cancelamento Autónomo via Token**: Links dinâmicos únicos baseados no ID do PostgreSQL enviados nas notificações. O cliente pode cancelar a sua vaga em 2 cliques sem necessidade de logins ou passwords.
*   **Algoritmo Caça-Vagas**: Sempre que uma vaga é cancelada (pelo cliente ou administrador), o sistema acorda em background, pesquisa cronologicamente na base de dados por clientes agendados em dias futuros para o mesmo horário e dispara um convite automático via WhatsApp/SMS oferecendo a antecipação.

---

## 🛠️ Stack Tecnológica

*   **Backend**: Python (Flask)
*   **Base de Dados**: PostgreSQL (Produção no Render) & Prisma ORM
*   **Engine de WhatsApp**: Evolution API (Node.js / Express)
*   **Interface**: HTML5, CSS3, JavaScript (Consultas Assíncronas / Fetch API)

---

## 📦 Arquitetura do Ecossistema

O projeto opera sob uma arquitetura de microsserviços interligados localmente e na nuvem:
1.  **Flask App (Porta 5000)**: Responsável pelas rotas, regras de negócio da barbearia, interface do cliente e painel administrativo.
2.  **Evolution API (Porta 8080)**: REST API em Node.js que interage de forma direta com o protocolo do WhatsApp, simulando digitação humana para proteção contra bloqueios (Anti-Ban).

---

## 🔧 Configuração e Instalação Local

### 1. Pré-requisitos
*   Python 3.10+
*   Node.js v20+

### 2. Clonar o Repositório e Instalar Dependências do Flask
```bash
git clone https://github.com
cd BF_Barbearia
python -m venv .venv
source .venv/bin/activate  # No Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Configurar as Variáveis de Ambiente
Cria um ficheiro `.env` na raiz do projeto Flask com o seguinte modelo (conforme explicitado no `.env.example`):
```text
FLASK_SECRET_KEY=A_TUA_CHAVE_SECRETA
DATABASE_URL=postgresql://utilizador:senha@servidor/banco
AUTHENTICATION_API_KEY=CHAVE_DE_CONEXAO_DA_API
```

### 4. Executar a Aplicação
```bash
python app.py
```
O site ficará disponível localmente em `http://localhost:5000`.

---

## 🔐 Segurança & Boas Práticas

*   **Proteção de Credenciais**: Ficheiros de ambiente contendo strings de conexão de bases de dados e tokens privados estão devidamente blindados e mapeados no `.gitignore`.
*   **Prevenção contra SQL Injection**: Toda a persistência e consulta de dados é realizada através do SQLAlchemy ORM, mitigando riscos de injeção de código malicioso.
*   **Tratamento de Strings**: Normalização rigorosa de números telefónicos no backend para o padrão internacional (E.164) antes do envio para gateways externos.

---

## 📄 Licença

Este projeto está sob a licença MIT. Sinta-se à vontade para clonar e utilizar como base para os seus próprios sistemas de agendamento.
