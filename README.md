# CardArena — Phase 1: Project Foundation

Multiplayer online card-game platform built with a server-authoritative architecture, FastAPI backend, React/Vite/Tailwind frontend, and PostgreSQL persistence.

---

## Quickstart & Local Development

### 1. Prerequisites
- **Python 3.12+**
- **Node.js 20+** & **npm**
- **Docker & Docker Compose**

---

### 2. Start PostgreSQL with Docker Compose
```bash
docker compose up -d
```
This spins up PostgreSQL 16 on port `5432` with database `cardarena`.

---

### 3. Setup and Run Backend
```bash
cd backend
python -m venv venv

# On Windows:
.\venv\Scripts\activate
# On Linux/macOS:
source venv/bin/activate

pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```
Backend health check: `http://localhost:8000/health`  
Interactive OpenAPI documentation: `http://localhost:8000/api/v1/openapi.json`

---

### 4. Setup and Run Frontend
```bash
cd frontend
npm install
npm run dev
```
Open `http://localhost:5173` in your browser.

---

### 5. Running Test Suites

**Backend Tests (pytest):**
```bash
cd backend
.\venv\Scripts\pytest -v
```

**Frontend Tests (Vitest):**
```bash
cd frontend
npm test
```

**Production Frontend Build:**
```bash
cd frontend
npm run build
```

---

## Phase 1 Implemented Features
* **Zero Client-Trust Architecture**: Backend dictates all game and room progression.
* **Cryptographic Deck**: Shuffling driven by `secrets.randbelow`.
* **Hidden Information Shield**: Opponents' private cards never leak over network payloads.
* **Multiplayer Room System**: Private code generation, seat management, duplicate-join handling, host privileges, host auto-transfer on leave.
* **Realtime WebSocket Protocol**: Low-latency state sync, ready state toggling, and reconnection recovery.
* **Modern Aesthetic UI**: Responsive glassmorphism interface built with Tailwind CSS and Lucide icons.
