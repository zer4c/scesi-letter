# API and Realtime Contracts

Base prefix: `/api`. All routes except health, invitation redemption, login,
and the correctly validated OAuth callback require an active session. JSON
field names and machine messages are English. UI translates error codes.

## Common Envelopes

Errors: `{error: {code, message, details?}, request_id}`. Never place secrets
in `details`. Common codes: `UNAUTHENTICATED`, `FORBIDDEN`, `VALIDATION_ERROR`,
`REVISION_CONFLICT`, `STALE_SUGGESTION`, `INTEGRATION_UNAVAILABLE`,
`SIGNATURE_LOCKED`, `RATE_LIMITED`, `DISPATCH_UNKNOWN`.

AI-specific recoverable codes include `ANALYSIS_INPUT_TOO_LARGE`,
`ANALYSIS_PRIVACY_BLOCKED`, and `PROVIDER_CONTRACT_ERROR`. `RATE_LIMITED` can
include sanitized `retry_after_seconds` and `scope="llm"`, without account IDs
or provider payloads. A queued analysis reports the same codes through its
actor-scoped job status. Local application quota rejection returns HTTP 429;
provider failures after queueing do not masquerade as successful suggestions.

Pagination: `?limit=20&cursor=...`, response `{items, next_cursor}`. Defaults
20, maximum 100. IDs use UUID strings; timestamps use ISO 8601 UTC. Reject
unknown privileged fields such as role or owner in ordinary create schemas.

Mutating save/render/sync/send APIs accept `Idempotency-Key`. Same key with same
payload returns the original result; same key with a different payload returns
409. Jobs return 202 with `{job_id, status}` and a scoped status route.

## Routes

| Method / path | Input | Output / authorization |
|---|---|---|
| GET /health | none | minimal readiness; no settings disclosure |
| POST /auth/login | email, password | session cookie and public user |
| POST /auth/logout | CSRF | revoke current session |
| GET /auth/session | none | public user, CSRF token |
| POST /auth/invitations | email | invitation link/token once; admin |
| GET /auth/invitations | none | admin; metadata/status only, never token hashes |
| DELETE /auth/invitations/{id} | CSRF | admin; revoke pending invitation |
| POST /auth/invitations/redeem | token, name, password | created user; intended identity only |
| GET /users | page, page_size | admin-only public membership page |
| PATCH /users/{id} | active?, role?, expected_revision | admin-only, revision-safe; role promotion transfers the singleton admin role |
| POST /auth/password/change | current_password, new_password, replacement_envelope? | atomic password/envelope handling |
| POST /auth/password/reset-invitations | user_id | recovery invitation; admin; no signature recovery |
| GET /signature | none | own encrypted envelope only |
| PUT /signature | password, typed envelope v1 | own upload/replacement after reauthentication |
| POST /auth/password/change | current_password, new_password, expected_envelope_updated_at, replacement_envelope? | compare-and-swap the signature envelope; re-wrap locally; returns envelope_updated_at; replacement required when one exists |
| POST /signature/authorizations | password, document_id, source_hash, version_id | one-use 60-second token; acting signer must own the envelope and have document access |
| GET /template | none | single current template with public settings |
| PATCH /template | settings, expected_revision | new immutable template revision; admin |
| POST /documents/preview | Markdown source | transient unsigned PDF; authenticated, no persistence or signature |
| GET /events | year?, pagination | authenticated event IDs and display names |
| GET /events/{id} | none | authenticated event details for retained document references |
| POST /events | name, year | authenticated; immutable normalized slug, duplicate conflicts |
| GET /contacts | q?, role?, institution?, career?, include_inactive?, pagination | authenticated shared directory; exact role/career/institution filters precede text matching |
| GET /contacts/{id} | none | current shared contact revision for conflict recovery |
| POST /contacts | typed contact | create validated contact |
| PATCH /contacts/{id} | fields, expected_revision | quick edit/deactivate; conflict-safe; no hard-delete endpoint |
| POST /contacts/import | connection_id | approved Google Contacts import job; P-05 |
| GET /events | year?, pagination | event IDs and display names |
| POST /events | name, year | sanitized immutable slug |
| POST /documents | metadata, body | unnumbered draft; no identifier or export job |
| GET /documents | page, page_size | only authorized documents |
| GET /documents/{id} | none | current snapshot/permissions and selected version status |
| POST /documents/{id}/participants | user_id | creator/admin policy |
| DELETE /documents/{id}/participants/{user_id} | none | revoke access, not document deletion |
| POST /documents/{id}/save | expected_revision, expected_source_hash | allocate if needed, checkpoint; version/job refs |
| POST /documents/{id}/checkpoint | CSRF | persist current authorized Yjs room snapshot without numbering an unnumbered draft |
| GET /documents/{id}/versions | none | immutable version summaries; authorized participant |
| GET /documents/{id}/versions/{version_id} | none | immutable metadata/status; authorized participant |
| GET /documents/{id}/versions/{version_id}/pdf | none | scoped binary PDF |
| GET /documents/{id}/versions/{version_id}/markdown | none | scoped UTF-8 Markdown |
| GET /jobs/{id} | none | actor-authorized export status and sanitized error code |
| POST /documents/{id}/versions/{version_id}/finalize | expected_pdf_hash | marks selected bytes sendable |
| POST /documents/{id}/sign?version_id=... | raw `image/png` body (2 MiB/4 MP maximum), `X-Signing-Authorization` header | synchronous render (20-second limit) to a new immutable, finalized version; no multipart spool, queued image, or saved standalone image |
| POST /documents/{id}/analyze/preview | expected_source_hash, kinds, manual_redactions? | locally redacted body and short-lived confirmation token; no provider request |
| POST /documents/{id}/analyze | expected_source_hash, kinds, preview_token, manual_redactions? | bounded two-pass graph; requires unchanged source and explicit preview confirmation |
| GET /documents/{id}/suggestions | source_hash | scoped structured suggestions |
| POST /documents/{id}/suggestions/{id}/accept | expected_source_hash, contact_id? | atomically applies one exact CRDT edit and decision; recipient-role proposals require a locally selected contact |
| POST /documents/{id}/suggestions/{id}/reject | none | marks one pending proposal rejected |
| GET /integrations | none | connection status; no token values |
| POST /integrations/google/connect | kind, mode | PKCE authorization URL; institutional requires admin; only approved scopes |
| GET /integrations/google/callback | code, state | authenticated session plus one-use state; encrypted tokens; account status only |
| PUT /integrations/{id}/root | folder_id | verify accessible Drive folder and select as institutional archive root; admin |
| POST /integrations/{id}/disconnect | none | own personal or admin institutional |
| GET /documents/{id}/versions/{version_id}/archive | none | archive job state and mapped immutable file IDs |
| POST /documents/{id}/versions/{version_id}/sync | topic_category?, confirm_miscellaneous? | retry idempotent archive job; miscellaneous requires explicit confirmation |
| POST /mail/send | document_id, version_id, connection_id, to, cc, bcc, subject, body, confirmed; `Idempotency-Key` | explicit confirmed dispatch job; selected version must be finalized and archived |
| GET /jobs/{id} | none | actor-authorized status, sanitized errors |

## Collaboration WebSocket

Connect to `/ws/documents/{id}` with the `yjs` subprotocol. The browser must
send the configured same-origin `Origin`; the existing active session and
CSRF cookies are required. The server negotiates only `yjs`. Messages use the Yjs sync and
awareness binary protocol; JSON lookalikes are rejected. Frames are limited to
1 MiB. The server revalidates the session and document membership at most every
15 seconds and before applying each update. A sync update is persisted before it
is applied to the live room or broadcast as its durable acknowledgement.

There is no document-delete route, generic signature decrypt route, or generic
arbitrary webhook-execution route. The demonstration `/automations/{id}/run`
route is removed; the only automation endpoint analyzes a scoped letter source.

Signature envelope fields use fixed protocol-v1 Argon2id parameters (64 MiB,
three iterations, one lane), AES-256-GCM, canonical Base64, 16-byte salts, and
independent 12-byte nonces. The API derives the owner ID from the session and
never accepts a target user ID for signature access.

The preview source is UTF-8 Markdown with a YAML front matter object containing
`document_type` and ISO `date`, with optional identifier, reference, salutation,
sender/recipient snapshots, topic, signoff, and template revision. Supported
body syntax includes headings, paragraphs, emphasis, `++underline++`, lists,
tables, fenced code, `::: center` blocks, and `\pagebreak`. Raw HTML and embedded
images are rejected; links render as labels only and never cause server fetches.

Creating a draft does not number or export it. The first explicit save assigns
the La Paz calendar year and the next atomic per-type counter, then stores the
numbered Markdown snapshot, version record, and queued render job in one MongoDB
transaction. Each later changed checkpoint creates a new version/job; unchanged
source reuses the current version. A stale revision returns `CONFLICT` unless it
is an identical retry of the already-current source.

Create/save `metadata` contains editable `LetterFields`; clients must not send
server-owned `identifier` or `template_revision`. The server preserves the
draft's selected template revision and locks the numbered type.

## Payload Details

`to`, `cc`, and `bcc` are arrays of validated addresses, deduplicated across
fields. Proposed limit: twenty unique addresses combined. `to` cannot be empty.
Reject CR/LF injection in addresses and subject. Sender derives from the chosen
verified connection. Never accept caller-supplied From or arbitrary attachments.

Suggestions contain `id`, `kind`, `source_hash`, `original`, `replacement`,
`start`, `end`, `reason`, and `status` for body edits; metadata suggestions use
`field` and typed replacement. Body offsets are Unicode code-point indices over
the exact normalized LF body. Convert explicitly in JavaScript; string UTF-16
offsets differ for some characters. Check original text as well as hashes.

Provider offsets refer to the redacted body, not the original document. The local
privacy adapter maintains a code-point span map and converts eligible ranges
back to original-source offsets before creating public suggestions. Reject
replacements crossing any protected placeholder, unrecognized placeholder,
ambiguous alignment, or mismatched text. The server computes public `original`
from its source snapshot; it never asks Groq to reconstruct private identities.
The user may add up to twenty non-overlapping manual redaction ranges, measured
as Unicode code points in the normalized body. Bind those ranges into the
short-lived privacy token and reproduce the same redacted bytes at analysis;
never accept modified client-supplied redacted text. Discard the mapping after
analysis, do not trace it. Apply the same restriction to metadata suggestions:
never invent or alter a sender identity. A recipient-role proposal may only
resolve to a user-selected, active local contact with the exact proposed role.

## Realtime

Connect to `/ws/documents/{id}` with the same session cookie and validated
Origin. Server checks membership before opening the room. Use a documented
Yjs-compatible binary sync/awareness protocol, validated in task T10. Do not
invent an incompatible JSON imitation of a CRDT.

Server revision/state vector is authoritative for persistence. Awareness carries
only participant display name, cursor, and color; it is transient. The server
broadcasts only data each participant is permitted to see.

Expose version/job events over authenticated SSE `/api/documents/{id}/events`
using `{type, document_id, version_id?, job_id?, status, revision}`. Do not send
email bodies, addresses/BCC, signing passwords/images, or provider payloads.

On disconnection, retain pending local edits in memory and indicate unsaved
state. Persist locally only with an explicit privacy decision. Reconnect uses
state vectors and reconciles acknowledged changes. Reject joining when access
is revoked; discard pending writes after displaying a clear loss-of-access state.

## Contract Artifacts to Implement Later

Generate an OpenAPI schema from typed FastAPI schemas and add a compact realtime
protocol fixture. The specs do not replace runtime validation. Include cross-
module contract tests for stale revisions, IDOR, role escalation, changed PDF
hashes, and tool-output schema validation.
