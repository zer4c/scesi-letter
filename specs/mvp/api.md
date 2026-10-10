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
| PUT /signature | typed envelope v1 | own upload/replacement after reauthentication |
| POST /signature/authorizations | password, document_id, source_hash, version_id | one-use 60-second token; owner only |
| GET /template | none | single current template with public settings |
| PATCH /template | settings, expected_revision | new immutable template revision; admin |
| POST /documents/preview | Markdown source | transient unsigned PDF; authenticated, no persistence or signature |
| GET /contacts | q?, role?, institution?, career?, include_inactive?, pagination | authenticated shared directory; exact role/career/institution filters precede text matching |
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
| GET /documents/{id}/versions | none | immutable version summaries; authorized participant |
| GET /documents/{id}/versions/{version_id} | none | immutable metadata/status; authorized participant |
| GET /documents/{id}/versions/{version_id}/pdf | none | scoped binary PDF |
| GET /documents/{id}/versions/{version_id}/markdown | none | scoped UTF-8 Markdown |
| GET /jobs/{id} | none | actor-authorized export status and sanitized error code |
| POST /documents/{id}/versions/{version_id}/finalize | expected_pdf_hash | marks selected bytes sendable |
| POST /documents/{id}/sign | version_id, authorization_token, PNG multipart | synchronous new signed version; no queued image |
| POST /documents/{id}/analyze | expected_revision, kinds | graph job / suggestion results |
| GET /documents/{id}/suggestions | source_hash | scoped structured suggestions |
| POST /documents/{id}/suggestions/{id}/accept | expected_source_hash | checked edit through collaboration/document service |
| POST /documents/{id}/suggestions/{id}/reject | none | proposal rejected |
| GET /integrations | none | connection status; no token values |
| POST /integrations/google/connect | kind, mode | authorization URL; institutional requires admin |
| GET /integrations/google/callback | code, state | validate state/session, connect correct account |
| POST /integrations/{id}/disconnect | none | own personal or admin institutional |
| POST /documents/{id}/versions/{version_id}/sync | none | retry idempotent archive job |
| POST /mail/send | version_id, connection_id, to, cc, bcc, subject, body | explicit confirmed dispatch job |
| GET /jobs/{id} | none | actor-authorized status, sanitized errors |

There is no document-delete route, generic signature decrypt route, or generic
arbitrary webhook-execution route. The old demonstration `/automations/{id}/run`
cannot return fictitious success once the MVP automation module replaces it.

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
Apply the same restriction to metadata suggestions: never invent or alter a
sender/recipient identity. Discard the mapping after analysis, do not trace it.

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
