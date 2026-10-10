# SCESI Academic Letter Platform

Local-first application for collaborative academic letters, Markdown/PDF
exports, owner-controlled signature images, recipient management, and approved
automation workflows. The implementation follows the modular-monolith and
security contracts in `specs/mvp/`.

## Technology

- Backend: FastAPI on Python 3.12, managed with Astral `uv`.
- Frontend: React 19 and Vite on Node.js 24, managed only with pnpm 11.19.0.
- Data: MongoDB replica set for transactions and persistent state.
- Runtime: Docker Compose, Nginx, and a private artifact volume.
- Background processing: one Python worker claims durable MongoDB jobs
  and writes immutable Markdown/PDF artifacts to the private Docker volume.

## Local setup

Requirements: Docker Compose v2, Node.js 24, and pnpm 11.19.0 for frontend
development. Python 3.12 and `uv` are needed to run backend commands directly.

Create the local environment file and start the application:

```bash
cp .env.example .env
docker compose up --build
```

Open `http://localhost:8080`. FastAPI's API documentation is at
`http://localhost:8000/docs`; readiness checks also verify the MongoDB replica
set at `http://localhost:8000/api/ready`. MongoDB is bound to loopback on port
27017 for direct backend development and is not exposed on other interfaces.

Before first use, generate a private rate-limit key with `openssl rand -hex 32`,
set `APP_RATE_LIMIT_KEY` in `.env`, and configure an initial administrator email
and passphrase (at least 12 characters). Then run
`docker compose exec backend uv run python -m app.modules.auth.bootstrap_admin`.
The bootstrap command creates an administrator only when no user exists; remove
the bootstrap password from `.env` afterward. Invitations are created by that
administrator in the authenticated API.

The first backend start seeds one default template revision from `.env` footer
settings. Administrators can change the phone list, footer URL, QR destination,
typography, margins, and display text through `GET/PATCH /api/template`; each
change creates a new immutable revision. Existing document versions keep their
original template revision.

Unsigned previews accept Markdown with safe YAML front matter at
`POST /api/documents/preview`; they are generated in memory and are not stored.

To run the Vite development server while the Compose backend/database are up:

```bash
cd frontend
corepack enable
corepack prepare pnpm@11.19.0 --activate
pnpm install --frozen-lockfile
pnpm run dev
```

Vite proxies API and WebSocket traffic to `http://localhost:8000`.

## Backend commands

```bash
cd backend
uv sync --frozen
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

The backend expects a reachable MongoDB replica set configured through the
repository-root `.env`. Use the Compose database for local development.

## Configuration and data

`.env.example` contains development-only placeholders. Replace the MongoDB
password before exposing services beyond the local machine. Provider credentials
are optional and must remain in `.env`; they are not copied into image layers or
the frontend bundle. Preserve the MongoDB data, MongoDB replica key, and artifact
volumes together when restarting or backing up Compose.

No real personal data, signatures, private phone numbers, or credentials belong
in this repository. See `AGENTS.md` and `specs/mvp/` before making changes.
