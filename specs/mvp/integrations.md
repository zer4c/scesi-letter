# Integrations, Configuration, and Operations

The sources below are authoritative starting points. Live official-site access
returned HTTP 403 during specification preparation. The user then supplied Groq
and Impeccable documentation; see `provider-notes.md` for source evidence and
conflicts. Documented behavior is not live account verification. Recheck during
task T00 and record a date.

## Groq and LangGraph

- Models: https://console.groq.com/docs/models
- Tool use: https://console.groq.com/docs/tool-use
- Quotas: https://console.groq.com/docs/rate-limits
- API key setup: https://console.groq.com/keys
- LangGraph: https://docs.langchain.com/oss/python/langgraph/overview

Create a personal Groq account, obtain a key in its console, and enter it only
into the untracked deployment `.env`. Evaluate `openai/gpt-oss-20b` first: supplied
docs list production status, local tools, and JSON mode. Verify Spanish output,
account access, and the selected structured response mode. The supplied quota
table lists 30 RPM, 1,000 RPD, 8,000 TPM, and 200,000 TPD for this model, with
ambiguous plan labeling described in `provider-notes.md`. These are provisional
Free defaults, not certified account allowances. No free plan guarantees
permanent availability.

Task T00 must record the model ID, observed availability, tool-call round trip,
context limit, RPM/RPD/TPM/TPD when published, output/schema support, and data
retention settings. Check the actual plan at `https://console.groq.com/settings/limits`
and resolve the pasted table's plan-label conflict. Record unknown fields as
unknown. Organization-specific
limits from the console take precedence over public defaults. No purchased plan
or paid fallback may activate automatically.

The LangGraph workflow is bounded:

`validate_source -> redact_locally -> classify -> propose_reference -> grammar/style
-> propose_role -> resolve_role_locally -> validate_suggestions -> return`.

Number allocation remains deterministic backend work. The graph can propose a
document type; it cannot issue sequence numbers. Role lookup is a local tool
with only role keys/counts exposed to the model; real contacts go directly to
authorized UI code. If local NER/redaction cannot meet SEC-010, skip provider
calls for that text until the user resolves the private segments. Return the
locally redacted body first. Require confirmation bound to user, source hash,
task kinds, redacted-body hash, and a short expiry before any provider call.

Initial application budgets: 2,000 estimated input tokens and 750 completion
tokens per pass, maximum two logical provider passes, 6,000 reserved tokens
including retries per analysis, thirty-second request timeout, and a sixty-second
total deadline. Input estimates include the complete transcript, system prompt,
tool schemas, and prior tool output; output reserves include reasoning usage.
Do not silently truncate letters. Return an explicit input-too-large state when
safe analysis cannot fit. These are application constraints, not provider quotas.

Gate every provider attempt with a shared organization/model allowance, not one
limiter per user. Reserve request and uncached token capacity atomically before
each attempt, including follow-ups/retries. Account conservatively for uncertain
timeouts and external account usage. Configured quotas and response headers
constrain calls; request headers report RPD and token headers report TPM. Maintain
RPM/TPD and any ITPM/OTPM separately. Honor 429/Retry-After; at most two retries
in total (four attempts maximum) inside both deadline and reserved token budget.
If the safe wait exceeds the deadline, return rate-limited and require a new
user analysis request rather than keeping the browser waiting indefinitely.
Never retry a contract 400 blindly or automatically switch model/plan.

For GPT-OSS use serial local tools, `include_reasoning=false`, proposed
`reasoning_effort="low"`, and no `reasoning_format`. Verify JSON/tool combinations
in T00; Pydantic validates all results. Do not enable built-in tools or remote
MCP. Return actionable failures instead of fake suggestions. No provider calls
on every keystroke. English versioned system prompts require Spanish user output.

## Google OAuth

- Setup and consent: https://developers.google.com/identity/protocols/oauth2
- Gmail scopes: https://developers.google.com/workspace/gmail/api/auth/scopes
- Send: https://developers.google.com/workspace/gmail/api/guides/sending
- Drive scopes: https://developers.google.com/workspace/drive/api/guides/api-specific-auth
- People contacts: https://developers.google.com/people/v1/contacts

Create a Google Cloud project, enable approved APIs, configure the OAuth consent
screen, register exact localhost redirect URIs, and add test users when required.
Store client secret and token encryption key in `.env`. A Google API key alone
does not authorize access to personal Gmail/Drive. Use the authorized OAuth flow.

Connect institutional Drive as the administrator and choose an accessible root.
Connect personal Gmail as its owner; connect institutional Gmail as the admin.
The mode labels permissions, not the Google account type. Never ask users to
share Gmail passwords, and do not rely on Gmail app passwords for this design.
For a delegated/shared Gmail alias, verify real send-as permissions; a configured
From string alone does not grant that authority. MVP can authorize the actual
institutional account directly.

Start with Gmail `https://www.googleapis.com/auth/gmail.send`, Drive
`https://www.googleapis.com/auth/drive.file`, and only approved People API
`https://www.googleapis.com/auth/contacts.readonly`. Verify exact supported
scopes/policy during T00. `drive.file` access is limited to selected/app-managed
files; prove selected root and folder traversal work. Do not silently upgrade to
full Drive/mailbox access. Gmail send-only cannot extract mailbox correspondents.

The connection flow uses state-bound PKCE (S256), requests only `openid`,
`email`, and the single provider scope needed for the connection, and rejects
scope sets that differ from the request. Personal mode is Gmail-only and visible
to that account owner. Institutional Gmail/Drive mode is administrator-only;
Drive root selection verifies that the folder is an accessible, non-trashed
Google Drive folder. The callback requires the same authenticated user that
started consent. Refresh tokens and PKCE verifiers are AES-GCM encrypted with
separate context-bound authenticated data.

Document consent/testing restrictions, token expiration/revocation, and any app
verification obligations observed in the current console. A testing-mode token
may require reconnection; do not promise permanent offline access.

## Drive Adapter

Use stable root/folder IDs and event IDs; do not navigate by folder names alone.
Cache parent/category mappings. Create folders idempotently and handle duplicate
names safely. Associate each uploaded file with app metadata including document
ID, version ID, artifact kind, and hash. Reconcile after a timeout before creating
another file. Mark a pair archived only after both files exist and match metadata.
Keep partial success visible and retry the missing side without overwriting.
Classify only from explicit letter type mappings; require a user-selected topic
when classification is ambiguous, and require explicit confirmation before using
the final-resort `miscellaneous` category. Folder mappings use stable event IDs,
so renaming an event never redirects a previous folder. A timed-out create is
reconciled by its app property before another create is attempted. If an
application-managed file is externally removed, report the missing mapping and
do not recreate or overwrite it silently.

Do not derive folder paths directly from untrusted names. Use a sanitized slug
and a stored event identity. Retain archived content when connections change.
If a Drive administrator moves/deletes files outside the application, report
the missing mapping; do not imply the application prevents all external deletion.

## Gmail Adapter

Generate standards-compliant multipart MIME with UTF-8 subject/body, plain-text
fallback, escaped optional HTML, optional approved public logo, and PDF bytes.
To/CC/BCC use recipient headers, with BCC omitted from user-facing shared views.
Set From using the verified account and allowed send-as identity. Test BCC
delivery behavior with controlled accounts; do not infer it from an HTTP success.

Store the encrypted dispatch payload only until processing/timeout recovery is
resolved, at most 24 hours initially. Keep job ID, actor, version/hash,
idempotency key, outcome, and timestamps for a proposed seven-day operational
window. Purge expired payloads without touching documents/Drive files. This is
operational deduplication, not a replicated Gmail history or signature audit.
The MVP stores dispatch content in a separate AES-GCM encrypted payload record
with a 24-hour TTL; BCC never appears in job/status responses or logs. Dispatch
jobs are claimed once. A timeout, provider 5xx, or expired running lease becomes
`unknown`; never retry a potentially submitted message automatically. Known
provider rejection becomes `failed` and requires a deliberate new user action.
Only a finalized, archived version with a matching archived PDF hash is
sendable. Institutional Gmail may be used by any active member, while only an
administrator can connect or disconnect that shared connection.

## Database and Collaboration Libraries

- Beanie: https://beanie-odm.dev/
- PyMongo Async: https://www.mongodb.com/docs/languages/python/pymongo-driver/current/
- Replica sets: https://www.mongodb.com/docs/manual/replication/
- Yjs: https://docs.yjs.dev/
- Python CRDT: https://github.com/y-crdt/pycrdt
- CodeMirror: https://codemirror.net/
- Impeccable: https://impeccable.style/tutorials/getting-started/
- Signature KDF: https://www.rfc-editor.org/rfc/rfc9106
- Browser AES-GCM: https://developer.mozilla.org/en-US/docs/Web/API/SubtleCrypto/encrypt

Retain Python 3.12 and Node 24 as the repository baseline. Resolve compatible
stable versions of Beanie/PyMongo/Pydantic, LangGraph/Groq, and Python/Yjs bridge
in task T00. Pin exact resolved dependencies in `uv.lock` and `pnpm-lock.yaml`.
Do not assume a Motor-based tutorial matches the selected current driver.

Use pnpm exclusively, pin its version in `packageManager`, and use
`pnpm install --frozen-lockfile` in Docker/CI. T01 migrates the existing legacy
lock/commands without running the forbidden package manager. Follow the supplied
Impeccable workflow in `provider-notes.md`: pinned pnpm installer, Codex/project
scope, reviewed `PRODUCT.md`, reusable `DESIGN.md`, and actual UI audit evidence.

## Future .env.example Contract

Create the real example file only in implementation task T01. It must contain
safe placeholders, English comments, and no real data. Load backend settings
from validated `core/config.py`; compose injects runtime variables into backend
and worker. Docker build layers receive no credentials. Frontend exposes only
explicit `VITE_*` public settings; same-origin APIs need no secret browser config.

| Variable | Meaning / safe example |
|---|---|
| APP_ENV | `development` |
| APP_TIMEZONE | `America/La_Paz` |
| APP_PUBLIC_URL | `http://localhost:8080` |
| API_PREFIX | `/api` |
| COOKIE_SECURE | `false` only for local development |
| ALLOWED_ORIGINS | explicit localhost origins |
| MONGODB_URI | replica-set URI with placeholders |
| MONGODB_DATABASE | `scesi_automation` |
| MONGO_ROOT_USERNAME / MONGO_ROOT_PASSWORD | local database credentials; blank secret example |
| BOOTSTRAP_ADMIN_EMAIL / BOOTSTRAP_ADMIN_PASSWORD | initial invitation administrator; blank placeholders |
| INTEGRATION_ENCRYPTION_KEY | independently generated 32-byte key; blank |
| INTEGRATION_KEY_ID | rotation label, e.g. `local-v1` |
| GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET | OAuth configuration; blank |
| GOOGLE_REDIRECT_URI | registered localhost callback |
| GOOGLE_DRIVE_ROOT_ID | approved root folder ID; blank |
| LLM_PROVIDER | `groq` or `disabled` |
| GROQ_API_KEY | blank secret |
| GROQ_MODEL | `openai/gpt-oss-20b`, candidate pending account verification |
| GROQ_REASONING_EFFORT / GROQ_INCLUDE_REASONING | `low` / `false` for the documented GPT-OSS adapter |
| GROQ_LIMIT_RPM / GROQ_LIMIT_RPD | provisional `30` / `1000`; verify organization and plan |
| GROQ_LIMIT_TPM / GROQ_LIMIT_TPD | provisional `8000` / `200000`; verify organization and plan |
| GROQ_LIMIT_ITPM / GROQ_LIMIT_OTPM | unset unless configured by the organization; never infer from total TPM |
| LLM_REQUEST_TIMEOUT_SECONDS | `30` |
| LLM_MAX_INPUT_TOKENS / LLM_MAX_OUTPUT_TOKENS | `2000` / `750`, complete per-pass application bounds |
| LLM_MAX_PASSES | `2` |
| LLM_MAX_ANALYSIS_TOKENS / LLM_MAX_RETRIES | `6000` / `2`, include retries and reasoning usage |
| ARTIFACT_ROOT | private backend volume mount |
| TEMPLATE_FOOTER_PHONES | `[]`; editable runtime defaults |
| TEMPLATE_FOOTER_URL / TEMPLATE_QR_URL | safe configurable public placeholders |
| TEMPLATE_FOOTER_EMAIL / TEMPLATE_FOOTER_ADDRESS | empty placeholders |
| EMAIL_LOGO_URL | user-approved public URL from D-assets |

Template changes stored as immutable DB revisions take precedence over initial
environment defaults. Never apply env bootstrap values over existing settings
at every restart. Invalid database/security configuration fails startup; missing
optional provider configuration marks the affected integration unavailable.

## Docker and Recovery

Services: `frontend`, `backend`, `worker`, `mongodb`, and a short-lived replica-set
initializer when needed. Backend and worker share one built monolith image.
Use named volumes for DB and artifacts. Readiness verifies migrations/indexes,
replica set, and worker leases; startup order alone is not sufficient.
Nginx supports WebSocket upgrades and SSE without response buffering.

Document backup and restore into a clean environment, including encryption key
handling. Interrupted idempotent exports/syncs recover; an interrupted Gmail
dispatch becomes unknown if delivery cannot be determined. Do not disable TLS,
checksums, signature verification, or broaden egress to make builds succeed.
