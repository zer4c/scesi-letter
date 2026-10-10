# Modular Monolith Architecture

## Runtime

React/Vite is served by Nginx. FastAPI is one application with domain modules.
A single background worker imports the same backend package and handles durable
jobs from MongoDB. MongoDB runs as a single-node replica set locally. Neither
the worker nor collaboration is a separate business service or microservice.

Production-like local access uses Nginx as one origin for `/api`, `/ws`, and
static UI. Development Vite proxies `/api` and WebSockets to FastAPI. Use one
backend instance for the MVP; a distributed collaboration coordinator is outside
scope. External boundaries are Google APIs and the configured LLM provider.

Frontend dependency/build commands use pnpm exclusively. Pin `packageManager`,
retain one `pnpm-lock.yaml`, and use frozen installs in containers/CI. Migrating
the existing package-lock and package-manager commands is task T01, before UI
implementation begins. No application migration is performed by these specs.

## Backend Boundaries

```text
backend/app/
  main.py
  core/
    config.py           # validated environment settings
    database.py         # replica set connection and migrations/indexes
    security.py         # sessions, password hashes, token encryption
    errors.py           # common error envelope
    jobs.py             # leases and durable job scheduling
    lifespan.py         # initialization and shutdown
  modules/
    auth/               # invitations, login, sessions
    user/               # membership and deactivation
    signature/          # owner-only encrypted envelopes
    template/           # default immutable template revisions
    contact/            # recipient directory and local role lookup
    document/           # drafts, numbering, snapshots, finalization
    collaboration/      # authenticated CRDT sessions/checkpoints
    automation/         # LangGraph analysis and suggestion decisions
    drive/              # archive adapter and folder mapping
    mail/               # personal/institutional OAuth and send adapter
    integration/        # OAuth state, token vault, connection status
  worker.py
```

For a domain, use `routes.py`, `controller.py`, `services.py`, `schemas.py`, and
`repository.py` only when each has a real responsibility. Routes wire HTTP;
controllers map requests and domain failures; services enforce rules;
repositories persist; schemas validate boundaries. Do not create empty user/auth
folders or layers merely to match an example.

Routes/controllers cannot access another module's collections directly.
Document services own numbering and snapshots. Collaboration asks document
services for checkpoints. Mail consumes immutable document artifacts. Automation
may read a privacy-filtered body and role vocabulary, not signature envelopes or
OAuth tokens. The signature module never exposes a general decrypt endpoint.

Keep all network calls behind adapters for deterministic testing. Shared `core`
must not accumulate domain policy or letter-specific rendering decisions.

## Frontend Boundaries

```text
frontend/src/
  App.jsx
  core/
    config.js           # public Vite settings only
    api.js              # same-origin transport, CSRF, errors
    auth/               # session state, guarded routes
    collaboration/      # transport and reconnect infrastructure
  shared/
    components/         # buttons, dialogs, fields, Bootstrap Icons
    styles/
  modules/
    auth/
    user/
    signature/
    document/
    contact/
    automation/
    integration/
    mail/
    template/
```

Each domain keeps its components, services, state/hooks, and contract types
together. Move the current automation demo API functions out of `core/api.js`
to `modules/automation/services/`; core is transport only. Keep JSX/JavaScript
for continuity. Runtime validation at API boundaries is required; switching the
whole frontend to TypeScript is a separate decision.

## Editing Pipeline

1. Authorized participant joins one Yjs document containing a Markdown body
   (`Y.Text`) and named metadata fields (`Y.Map`).
2. Python room applies updates, tracks server revision, and persists updates
   before acknowledging them. A reconnect can recover acknowledged changes.
3. Persist a compact CRDT state periodically; delete only compacted transient
   updates, never document versions. Test crash/replay before enabling compaction.
4. A bounded debounce checkpoints canonical source through the document module.
5. MongoDB transaction records a source snapshot, version, and export job.
6. Worker renders Markdown/PDF into private persistent artifact storage.
7. Drive job archives both immutable files. UI receives authenticated status
   updates and displays local versus archived readiness.

Out-of-order preview responses cannot replace a preview for a newer revision.
Preview is unsigned, on-demand, debounced, cancelable, and not a Drive export.
Use local downloads while sync is pending; sending requires archive readiness.

## Rendering

Start with fpdf2 and the retained OFL fonts. Support paragraphs, headings,
bold/italic/underline, lists, data blocks, centered text, page breaks, and Spanish
characters. The renderer consumes typed metadata and configuration; never execute
Markdown, fetch arbitrary embedded images, or accept caller filesystem paths.

Use Letter paper initially, repeated gray header/red footer, left UMSS and right
SCESI logos, centered institutional lines, and the supplied visual references.
Initial margins and sizing should match the previous academic design where known:
30 mm side margins, about 36.8 mm header and 28.3 mm footer, 11 pt body font.
Confirm actual fidelity with approved assets; these dimensions are seed defaults.

Keep the signature slot fixed above the footer/signoff. Reject a signature that
cannot fit; do not cover body text or footer. Arbitrary drag/drop placement is
deferred. Embed fonts/assets for stable output. Render snapshots with fixed dates
and deterministic settings; store first produced bytes as the source of truth.
The signing endpoint accepts a bounded raw PNG body rather than multipart so the
image remains in process memory; the opaque authorization travels in a header,
not a URL. Limit images to 2 MiB and 4 megapixels and bound render execution to
20 seconds. A signed version is finalized as part of successful render.
