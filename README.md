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

For Google connections, configure the OAuth client ID/secret and register the
exact `GOOGLE_REDIRECT_URI`. Generate a separate token-encryption key with
`openssl rand -base64 32` and set it as `INTEGRATION_ENCRYPTION_KEY`. Never reuse
the rate-limit key or signature password as this key. Gmail and Drive access
remain unavailable until these settings and the approved Google APIs are
configured; personal connection tokens are visible only to their owner.

To enable letter-assistance previews, generate a separate
`AI_PREVIEW_SIGNING_KEY` with `openssl rand -hex 32`. The Spanish spaCy NER model
runs locally; the app displays its redacted body and requires confirmation before
any provider call. To opt into Groq, create a key at
`https://console.groq.com/keys`, set `GROQ_API_KEY`, and explicitly change
`LLM_PROVIDER=disabled` to `LLM_PROVIDER=groq`. `openai/gpt-oss-20b` is the
configured candidate, not a promise of free-plan access. Confirm the current
account's model eligibility and limits at `https://console.groq.com/settings/limits`;
the sample quota values in `.env.example` are provisional. No provider calls
occur with the default disabled setting.

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

Verify JavaScript/Python CRDT update, metadata-map, state-vector, and reconnect
compatibility with `pnpm run interop:crdt` from `frontend/`.

## Backend commands

```bash
cd backend
uv sync --frozen
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

The backend expects a reachable MongoDB replica set configured through the
repository-root `.env`. Use the Compose database for local development.

## Configuration and data

`.env.example` contains development-only placeholders, including a known
MongoDB password and non-random key samples. Never deploy it unchanged or treat
it as a secrets file. Replace keys and passwords in the ignored `.env` file;
provider credentials are optional and are supplied at runtime, not baked into
images or the frontend bundle. Preserve the MongoDB data and artifact volumes
together. Use [docs/operations.md](docs/operations.md) for worker recovery,
backup, and an isolated restore drill.

No real personal data, signatures, private phone numbers, or credentials belong
in this repository. See `AGENTS.md` and `specs/mvp/` before making changes.

For worker recovery, encrypted backup handling, and an isolated restore drill,
see [docs/operations.md](docs/operations.md).
