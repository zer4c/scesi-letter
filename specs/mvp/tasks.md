# Implementation Tasks for a Small Model

Each task is a reviewable slice. Implement tasks independently; do not combine
the whole MVP into one large commit. Each commit example is at most 50 characters.
Read the files listed in the card, plus `/AGENTS.md`, before implementation.
Use `docs/*` for specification-only work and `feature/*` for new capabilities.

## Dependency and Commit Map

| Task | Depends on | Branch | Suggested commit |
|---|---|---|---|
| T00 Provider/library verification | none | docs/provider-verification | docs: verify provider capabilities |
| T01 Validated config and local runtime | T00 library decisions | feature/runtime-config | feat: configure local runtime |
| T02 Typed persistence and invariants | T01 | feature/persistence | feat: add typed persistence |
| T03 Invitations and sessions | T02 | feature/invitation-auth | feat: add invitation authentication |
| T04 Admin membership lifecycle | T03 | feature/member-management | feat: manage invited members |
| T05 Recipient directory API | T03 | feature/recipient-directory | feat: add recipient directory |
| T06 Default template revisions | T02, assets P-02 for fidelity | feature/default-template | feat: configure default template |
| T07 Unsigned PDF rendering | T06 | feature/document-rendering | feat: render academic letters |
| T08 Numbering and source snapshots | T03, T07 | feature/letter-versioning | feat: version numbered letters |
| T09 Durable worker and artifact spool | T08 | feature/artifact-jobs | feat: persist document artifacts |
| T10 Collaboration protocol spike | T03, T08 | feature/collaboration-protocol | feat: add collaborative document sync |
| T11 Auth UI and navigation | T03, P-03 | feature/auth-ui | feat: add account access screens |
| T12 Collaborative editor and preview | T07, T09, T10, T11 | feature/document-editor | feat: add collaborative letter editor |
| T13 Client signature envelopes | T03, T11 | feature/signature-encryption | feat: encrypt personal signatures |
| T14 Owner-authorized signed render | T08, T09, T13 | feature/signature-rendering | feat: authorize signature rendering |
| T15 Google connection vault | T03, T04, T11 | feature/google-oauth | feat: connect Google accounts |
| T16 Drive archive adapter | T09, T15 | feature/drive-archive | feat: archive letter versions in Drive |
| T17 Privacy filter and graph engine | T05, T08, T09, T00 P-01 | feature/letter-assistance | feat: add private letter assistance |
| T18 Suggestion review UI | T12, T17 | feature/suggestion-review | feat: review letter suggestions |
| T19 Recipient quick editing UI | T05, T12 | feature/contact-editor | feat: edit recipients inline |
| T20 Approved contact import | T05, T15, P-05 | feature/google-other-contacts-import | feat: import Google contacts |
| T21 Gmail delivery service | T09, T14, T15, T16 | feature/gmail-delivery | feat: send finalized letter PDFs |
| T22 Finalization and composer UI | T12, T14, T21 | feature/mail-composer | feat: compose institutional emails |
| T23 Organization settings UI | T04, T06, T15 | feature/organization-settings | feat: manage organization settings |
| T24 Recovery and operational setup | T09, T16, T21 | chore/runtime-recovery | chore: document recovery procedures |
| T25 Integrated release checks | all required tasks | chore/mvp-release | test: verify MVP release workflows |

T00 external-provider failures do not prevent local configuration/persistence work
after compatible library decisions are made; do not claim T00 fully complete.

## Task Cards

### T00 — Verify Dependencies and Provider Facts

Read `decisions.md`, `integrations.md`, and `provider-notes.md`. Start from the
supplied official evidence; do not repeat research already captured. Record
current official links/date and resolve the rate-table plan-label conflict,
Groq free-model/quota/tool/schema facts, Google scopes/root selection, Beanie
driver compatibility, CRDT compatibility, browser Argon2 library, and Impeccable
availability. A real Groq tool round trip requires securely injected credentials;
do not ask for keys in chat. Record unavailable verification as a prerequisite.
Deliver a narrow verification note with approved pinned-version choices, without
modifying application code. Gate: P-01/P-03 status is honest and traceable.

### T01 — Configure the Local Monolith Runtime

Read `architecture.md`, `integrations.md`, and SEC-002 in `security.md`. Implement validated settings,
safe `.env.example`, ignore rules, backend/worker image entrypoints, and MongoDB
replica-set initialization. Keep frontend/back same-origin; configure Vite and
Nginx proxy for HTTP/WS/SSE. No features or production VPS work. Checks: missing
required secrets fail predictably; build layers/frontend bundle contain no secret;
Compose validates and repeated startup initializes the replica set safely.

Migrate JavaScript tooling to pnpm before any frontend installation: pin
`packageManager`, use `pnpm import` if the existing lock is compatible, review
resolved versions, then remove the superseded lock. Otherwise resolve using
pnpm and review the dependency diff. Update README/scripts/Docker/CI/setup to
pnpm equivalents; commit exactly one JavaScript lockfile, `pnpm-lock.yaml`.
Never execute the old package-manager commands. Checks: frozen clean pnpm
installation/build, reproducible image/CI commands, and no forbidden invocations.
Keep this tooling migration a separate atomic substep from runtime services.

### T02 — Persist Typed Documents and Indexes

Read `data-model.md`. Add Beanie/Pydantic documents, module-owned repositories,
index installation, transaction helpers, and migrations/version checks. Introduce
collections when the owning feature needs them, not unused bulk endpoints.
Checks: duplicate keys, singleton admin, unknown fields, counter transactions,
restart persistence, and transaction rollback against real local MongoDB.

### T03 — Invitation Authentication

Read BR-001, SEC-001..004, auth contracts. Implement bootstrap once, invitation
issue/redemption, Argon2 login, opaque sessions, logout, CSRF, expiry, and rate
limits. Add reset invitation handling with unrecoverable-signature semantics.
Checks: expired/replayed invite, concurrent redemption, role injection, wrong
password, blocked brute force, CSRF, session expiry, and bootstrap repeatability.

### T04 — Manage Membership Safely

Read BR-002..004 and singleton role rules. Implement invitation management,
atomic administrator transfer, account deactivation, session revocation, and
retained-document access policy. Do not add signature admin endpoints or document
deletion. Checks: two concurrent admin promotions, last-admin removal, disabled
user API/WS rejection, retained documents, admin envelope access denied.

### T05 — Recipient Directory

Read BR-017, contact schema/contracts. Implement validated contact CRUD without
hard deletion, revision-safe edits, structured role/career/institution lookup,
pagination, and duplicate reconciliation. Use synthetic example identities only.
Checks: ambiguous academic role, stale edit, normalized duplicate email, and
contact updates not retroactively changing source snapshots.

### T06 — Configure One Default Template

Read BR-005, asset exception, architecture rendering notes. Add single template
settings/revisions, public logos once usable assets arrive, configurable footer
phones/links/address/QR, allowed typography/margins, and fixed signature slot.
Generate QR locally. Checks: previous revisions immutable, no phone baked into
PNG/source fixtures, invalid URL/path/resource rejected. P-02 blocks fidelity
signoff, not typed settings. Do not restore deleted personal assets/history.

### T07 — Render Unsigned Academic PDFs

Read BR-006, architecture rendering, SEC-014. Implement safe YAML serialization,
supported Markdown blocks, fpdf2 header/footer/page layout, bundled font loading,
and private unsigned preview. No contacts, signatures, or provider requests.
Checks: long letter/page breaks, Spanish text, all supported syntax, headers and
footers on every page, invalid front matter, large input, external image and path
injection rejection. Verify actual PDF text/pages and visual layout.

### T08 — Allocate Codes and Version Source

Read BR-007..013 and atomic operations. Implement draft metadata, participant
policy, event/topic mapping, first-explicit-save numbering, immutable source
snapshots, no-op hash detection, finalization state, and idempotency. No Drive
calls yet. Checks: simultaneous first saves, yearly rollover, independent type
counters, locked type, no duplicate IDs, no versions on unchanged save, source
mutation never overwrites prior snapshot, IDOR denied.

### T09 — Render Jobs and Durable Artifacts

Read BR-009..012, jobs/artifact model. Implement one MongoDB worker with leases,
export scheduling, integrity hashes, versioned file storage, retry state, and
scoped job/artifact endpoints. Preview remains transient. Checks: worker crash,
reclaim/render recovery, duplicate enqueue, unrelated artifact access denied,
prior MD/PDF bytes unchanged, persisted files survive restart.

### T10 — Prove and Add CRDT Collaboration

Read collaboration contracts. First make a two-client JavaScript Yjs/Python
binary interop fixture, including metadata map, body text, state vector, and
reconnect. Only then wire authenticated document rooms, durable update ACK,
snapshots, bounded checkpoint debounce, awareness, and access revocation.
Protect locked metadata on the authoritative server; client-side disabled fields
alone are insufficient. Checks: simultaneous edits converge, malformed/oversized
updates fail safely, crash replays ACKed changes, unauthorized room join/reconnect
fails, disabled membership closes sessions, invalid metadata cannot persist.

### T11 — Session Screens and App Navigation

Read `ui.md`, `provider-notes.md`, and the actual installed Impeccable instructions.
Pin/install with pnpm only, choose Codex/project scope, reload and verify skills;
review `PRODUCT.md` and retain reusable rules in `DESIGN.md`. Do not claim UI
skill use if installation/discovery is unavailable. Implement invitation/login/session
screens, guarded routes, session expiry messages, and shared accessible primitives.
No editor redesign. Checks: keyboard/focus, loading/error state, auth restoration,
logout, admin-only route rejection on server and UI. Frontend build must pass.

### T12 — Academic Collaborative Editor

Read editor UI, BR-005..013, CRDT contracts. Add document list/create, CodeMirror
body, collaborative structured fields, participant controls, debounced preview,
checkpoint status, event/topic selection, Save, and mobile Edit/Preview tabs.
Checks: two-browser editing, newest-preview wins, disconnect/reconnect, first
Save numbering, stale-save conflict, no template chooser, no Delete document.
Do not wire automatic AI/email side effects into editor autosave.

### T13 — Encrypt the Owner's Signature

Read SEC-005/009 and envelope schema. Implement maintained Argon2id browser
derivation, DEK wrapping, AES-GCM envelope upload/retrieve, own-signature settings,
password change/re-wrap, and recovery replacement. No signed PDFs yet.
Checks: decrypt known synthetic image, wrong password/tamper/AAD/nonce tests,
owner isolation, no plaintext in request logs/storage, forgotten password cannot
recover envelope. Benchmark supported browser/memory limits and document results.

### T14 — Authorize and Render a Signed Version

Read SEC-006..008, BR-011/012. Implement one-use bound authorization, transient
owner image upload, synchronous fixed-position signed PDF, new immutable version,
and signed-finalization behavior. Do not enqueue plaintext images. Checks: token
expiry/reuse, wrong user, stale source, simultaneous edit, signature overflow,
own-only signing, signed PDF privacy limitation documented, storage/log scan.

### T15 — Store Google Connections Securely

Read SEC-012/013 and OAuth configuration. Implement consent URL/state/callback,
personal versus institutional connection policy, encrypted refresh tokens,
refresh/disconnect, root selection, and scoped connection status. No email sends
or archive writes yet. Checks: replay/expired/wrong-user state, revoked tokens,
scope mismatch, independent personal/institutional connections, key unavailable.
Actual account round trips require P-04; mocked checks are not live evidence.

### T16 — Archive Both Files in Drive

Read BR-018..020 and Drive adapter. Implement folder-ID mapping, year/event/topic
placement, pair upload, timeout reconciliation, minimal app properties, archive
status, and manual retry. No delete/overwrite endpoint. Checks: partial pair retry,
duplicate job, renamed event slug, external missing file, account disable retains
archive, real Drive both-file upload with approved root.

### T17 — Build Private LangGraph Assistance

Read BR-014..016, SEC-010/011, `provider-notes.md`, and graph budgets. Implement local redaction/NER gate,
versioned system prompts, bounded graph nodes/tools, structured suggestions,
classification/reference, local role resolution, quota handling, and fake adapter.
Remove/replace the demonstration's fake completed automation behavior. Checks:
spy adapter sees no names/contacts/signatures/templates, tool injection denied,
invalid model JSON rejected, timeout/quota safe, number never allocated by model.
Real model/tool free-plan confirmation remains P-01.
Checks also cover serial tool execution with exact tool-result IDs, GPT-OSS
reasoning/JSON parameter compatibility, organization-wide concurrent quota
reservations, RPD/TPM header interpretation, optional ITPM/OTPM, restart-safe
budgets, bounded retries, and no paid/provider-hosted-tool fallback.

### T18 — Review Suggestions in the Editor

Read suggestion API/UI and offset contract. Add annotations/panel, individual
accept/reject, role candidate selection, privacy-redaction correction, and stale
proposal handling. Accepted suggestions flow through the CRDT/document service.
Checks: exact text replacement, Unicode offsets, collaborator changed text,
double acceptance, provider-disabled manual workflow, no automatic Apply all.
Include redacted-to-source span fixtures with different-length names/placeholders,
adjacent masked spans, and a forbidden correction crossing an identity placeholder.

### T19 — Edit Contacts with Few Clicks

Read contact UI. Add structured autocomplete, Bootstrap pencil quick edit,
candidate disambiguation, inline save-new-contact, and conflict UI. Checks:
keyboard navigation, return focus, unchanged letter snapshot after directory
edit, ambiguous role requires selection, server validations visible.

### T20 — Import the Approved Contact Source

Import Google “Other contacts” through People API with only
`contacts.other.readonly`; never read Gmail messages. Paginate source previews,
show name/email only, collect required academic role and institution, and add
only explicitly selected records after confirmation. Mark existing emails and
skip duplicates without overwriting. Checks: pagination, duplicate races,
denied/revoked scope, private fields excluded, no mass silent overwrite.

### T21 — Send Finalized PDFs Through Gmail

Read BR-021..023, mail contract, SEC-015. Implement sender authorization, safe
MIME, PDF-only attachment, To/CC/BCC, operational dedup, and unknown-outcome
handling. No remote send is authorized during development until a controlled
test is explicitly requested/configured. Checks: personal and institutional
accounts, invalid From/headers, stale/nonfinal/unarchived version rejected,
double submit one upstream call, timeout no automatic retry, BCC delivery and
Markdown absence verified with controlled test accounts.

### T22 — Finalize and Compose Email

Read signature/save/mail UI. Add explicit version selection, unsigned or signed
finalization, sender picker, To/CC/BCC controls, subject/short body, PDF display,
optional public logo, final confirmation, and unknown-delivery state.
Checks: correct selected PDF/hash sent despite newer draft, recipient confirmation,
keyboard usability, signed-version retention, repeated click suppressed, personal
account absent handled, existing Gmail history used without a duplicate UI.

### T23 — Organization Settings

Read admin UI, template and integration rules. Add invitations/member status,
atomic admin transfer, default-template/footer settings, institutional Gmail and
Drive configuration/status. Checks: user denied admin controls, no another-user
signature access, phones editable and absent from Git, settings revisions do
not rewrite existing PDFs.

### T24 — Document and Exercise Recovery

Read local operations/integrations. Write English setup instructions with exact
OAuth/Groq/key-generation links, safe `.env.example` explanation, local Docker
startup, backup/restore, worker recovery, expired credential reconnect, and mail
unknown-result handling. Update README's obsolete no-database/demo language.
Checks: new local environment starts from documented steps, restored MongoDB and
artifact hashes match, admin bootstrap does not reset users, dependency locks
remain frozen, secrets absent from files/build/logs.

### T25 — Verify the Release as a Whole

Read `acceptance.md`. Run critical security/concurrency/recovery cases against
the real local runtime and two browser sessions. Record provider live tests as
passed/failed/unrun, not mocked success. Verify all BR/SEC rules have coverage,
no emoji/other icon library/non-English engineering identifiers, and no private
data/assets in Git. Do not fix unrelated features in this task; return defects
to their domain branches. Missing prerequisites prevent full MVP readiness.
