# 💈 BF Barbearia - Smart SaaS Scheduling & Autonomous Spot-Recovery System
 
🌐 **Live Application URL:** [https://bf-barbearia.onrender.com/](https://bf-barbearia.onrender.com/)

This repository contains the full enterprise-ready ecosystem for **BF Barbearia**, a multi-tiered SaaS platform designed to completely automate barbershop scheduling, eliminate no-shows, and optimize slot utilization. 

By operating via a direct local interface with the **Evolution API**, this system achieves **absolute zero message cost**, completely bypassing Meta's official WhatsApp Business API messaging fees. It features an autonomous backend engine that drives reactive queue manipulation to rescue cancelled slots in real time.

---

## 🚀 Core Features & Advanced Algorithms

### 1. The Spot-Recovery Engine ("Caça-Vagas")
When a booked slot is cancelled via the customer UI or administrative dashboard, a background transactional worker wakes up. 
* It scans the PostgreSQL database chronologically to find clients booked for identical time slots in future dates.
* It selects the most optimal candidates and triggers sequential, time-limited (30-minute window) invitations via WhatsApp.
* It utilizes a stateful cascade state machine (`active` ➔ `em_proposta` ➔ `ativo` / `caça_vagas_recusado`) to move through the queue autonomously if a user rejects the offer or times out.

### 2. Multi-Tenant Concurrency Control (Anti-Overbooking)
To prevent double-booking when the autonomous WhatsApp engine and manual reception desk interact simultaneously:
* The system injects a strict database-level row lock using SQLAlchemy's `.with_for_update()`.
* The target PostgreSQL row is locked for the duration of the "YES" confirmation transaction block, forcing concurrent reads into a thread-safe queue.

### 3. Passwordless Tokenized Cancellations
* Eliminates the barrier of user logins and passwords. 
* Cancellations are authorized via dynamic, cryptographically secure URL tokens generated using `secrets.token_urlsafe(16)`.
* This completely eliminates resource-scanning vulnerabilities (sequential ID scraping) and complies with modern privacy-first architectures.

### 4. Smart Calendar Engine & Load Balancing
* **Time-Gated Guard**: Prevents historical scheduling by cross-referencing timestamps with `Europe/Lisbon` timezone constraints.
* **Workload Balancer**: Features a dynamic routing algorithm that distributes appointments equally among available staff when the client selects "Any Barber (Fastest)".

---

## 🛠️ Technological Stack

* **Backend & Business Logic**: Python (Flask via the *Application Factory* design pattern)
* **Database Layer & Schema Migrations**: Remote PostgreSQL (Production) / Ephemeral cloud PostgreSQL mapped via Prisma Data Platform / Flask-SQLAlchemy
* **Async Engine**: APScheduler (`BackgroundScheduler`) managing concurrent temporal threads
* **Messaging Middleware**: Evolution API v2 (Node.js / Express Architecture)
* **Frontend**: HTML5, CSS3, Vanilla JavaScript (Asynchronous requests via Fetch API / DOM manipulation)

---

## 📦 Microservices Architecture

The system operates across a distributed multi-runtime environment:
1. **Flask Application (Production Port)**: Handles HTTP routing, core business constraints, Jinja2 template compiling, and database transactional updates.
2. **Evolution API Microservice (Port 8080)**: An independent Node.js REST API handling raw WhatsApp socket management, mimicking human interaction behaviors (such as automated typing delay statuses) to prevent carrier anti-spam bans.

---

## 🔧 Local Environment Installation

### 1. Prerequisites
*   Python 3.10+
*   Node.js v20+

### 2. CSetup the Flask Backend
```bash
# Clone the repository
git clone https://github.com
cd BF_Barbearia

# Checkout the development branch
git checkout dev

# Initialize virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows use: .venv\Scripts\activate

# Install required dependencies
pip install -r requirements.txt
```

### 3. Environment Configuration
Create a `.env` file in the root directory of the application:
```env
# Flask Core
FLASK_SECRET_KEY=your_secure_session_key_here

# Database URIs
DATABASE_URL=postgresql://user:password@host:port/dbname
DATABASE_PRIVATE_URL=postgresql://user:password@internal-host:port/dbname

# Microservice Integrations
EVOLUTION_API_URL=https://ngrok-free.dev
AUTHENTICATION_API_KEY=your_shared_evolution_api_key

# Webhook Protections
WEBHOOK_TOKEN=your_secure_hmac_handshake_token
URL_PUBLICO_SaaS=https://onrender.com
```

### 4. Database Initialization
```bash
# Push schema schemas and validate tables
npx prisma db push --schema=./prisma/postgresql-schema.prisma
python app.py
```
The site will spin up locally on `http://127.0.0.1:5000`.

---

## 🔐 Implemented Security Measures (Audit Compliance)

The architecture strictly complies with standard web vulnerability mitigation practices:
* **XSS Eradication**: All text displays were migrated out of raw python strings into strict, auto-escaped Jinja2 blocks.
* **Timing Attack Hardening**: Administrative and webhook routing keys are evaluated via `secrets.compare_digest` to prevent byte-by-byte timing attacks on string variables.
* **CSRF Mitigation**: Global application protection is governed by `Flask-WTF`. Asynchronous JavaScript actions inject the security signing via the `X-CSRFToken` header.
* **Cookie Isolation**: Session storage cookies are hardened with strict production parameters: `HttpOnly=True`, `Secure=True`, and `SameSite='Lax'`.
* **Webhook Signature Validation**: The endpoint `/webhook/confirmar-antecipacao` runs a secure token comparison, immediately blocking arbitrary wildcards or spoofed network inputs.

---

## 📄 License

This software ecosystem is open-source, licensed under the **MIT License**.