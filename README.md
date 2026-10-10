# SCESI Automation Platform

Base platform for institutional automations, with no database and no personal
data included in the repository.

## Stack

- Backend: FastAPI, Python 3.12 y `uv`.
- Frontend: React 19, Vite y Node.js 24.
- Ejecución: Docker Compose y Nginx como proxy del frontend.
- State: process memory; it is lost on restart because there is no database yet.

## Desarrollo local

Backend:

```bash
cd backend
uv sync
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Frontend:

```bash
cd frontend
corepack enable
corepack prepare pnpm@11.19.0 --activate
pnpm install --frozen-lockfile
npm start
```

The API is available at `http://localhost:8000/docs` and the Vite application
at `http://localhost:5173`.

## Docker

```bash
docker compose up --build
```

The application is available at `http://localhost:8080`; Nginx proxies `/api`
to the backend.

## Automatizaciones

The API exposes in-memory automation creation, listing, and execution:

- `GET /api/health`
- `GET /api/automations`
- `POST /api/automations`
- `POST /api/automations/{id}/run`

Actions are intentionally safe and demonstrative for now. Each real action must
be implemented as an explicit, validated adapter.
