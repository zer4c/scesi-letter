# Requirements and Business Rules

## Product Goal

Invited academic organization members collaborate on institutional letters,
review AI suggestions, generate Markdown/PDF pairs, optionally apply their own
signature image, organize the files in Google Drive, and send the PDF through
personal or institutional Gmail. Typical letters request classrooms, furniture,
permissions, or invite participants to academic activities.

## Included Capabilities

- Invitation-only accounts and at most one administrator.
- A single default template with header/footer and fixed signature position.
- A structured form plus Markdown editor and adjacent PDF preview.
- Authenticated multi-user real-time editing and reconnect recovery.
- Automatic Spanish dates and references, deterministic letter identifiers.
- One encrypted signature image per user; password required for every use.
- Shared structured recipient directory, autocomplete, quick editing, and
  suggestions by academic role.
- LangGraph assistance for grammar, style, references, document classification,
  and recipient-role suggestions, with individual human approval.
- Versioned Markdown/PDF pairs and automatic Google Drive synchronization.
- Personal and institutional Gmail senders, PDF attachment, To/CC/BCC, editable
  subject and short body, and explicit final send confirmation.
- Local Docker Compose and documented configuration for external providers.

## Identity and Permissions

**BR-001** Registration requires a valid, single-use, unexpired invitation.
The initial administrator is bootstrapped from deployment configuration. Normal
registration never accepts a caller-supplied role.

**BR-002** There is at most one administrator. The administrator invites users,
changes membership, disables accounts, configures institutional integrations,
and edits template configuration. All active users may create documents.
There is no read-only role. A collaborator is an explicit document participant.

**BR-003** Account removal means deactivation. Keep the account ID, documents,
versions, and Drive files. A disabled account cannot use HTTP, WebSocket, OAuth,
or signature endpoints. Existing documents remain available to their active
participants and the administrator for document management.

**BR-004** A user owns exactly one active signature envelope. No administrator
endpoint may read, decrypt, export, replace, or apply another user's envelope.
Disabling an account does not require deleting its envelope or documents.

## Editing, Numbering, and Versions

**BR-005** Every new document uses the one default template. No template chooser
or template creation UI is included. Template changes affect future snapshots,
not previously exported PDFs.

**BR-006** Canonical source consists of structured metadata and a Markdown body.
The form and editor are synchronized. Persist source as UTF-8 `.md` with safe
YAML front matter; export PDF only for delivery. No DOCX.

**BR-007** Use `<TYPE>-SCESI-<YEAR>-<SEQUENCE>`; initial types are `INV`, `SOL`,
`MEM`, `ACT`, `PRES`, `CIRC`, `NOT`, and `GEN`. A normal request uses `SOL`;
classroom/furniture are topics, not additional numbering families. Treat `ACT`
as an activity communication, without implying a legally certified meeting
record. The sequence is independent per organization, type, and year, padded
to at least three digits and allowed to exceed 999.

**BR-008** Assign the identifier at the first explicit Save. Background draft
autosave does not consume a number. Use `America/La_Paz` to determine the year
at allocation. Keep the identifier permanently; changing letter date, topic,
event, or year later never reallocates it. Lock its type after allocation.
Creating another type requires a new document. Gaps are acceptable; duplicates
and number reuse are not. The LLM suggests the type, never the sequence.

**BR-009** Each changed persisted source checkpoint creates a new immutable
version. Batch concurrent keystrokes into a checkpoint after two seconds of
inactivity, with a maximum ten-second delay. An explicit Save checkpoints
immediately. Identical content/configuration produces no extra version.
Ephemeral keystrokes and cursor updates do not each create an export.

**BR-010** Numbered checkpoints automatically produce immutable `.md`/`.pdf`
pairs and queue Drive synchronization without another confirmation. Before
numbering, retain draft checkpoints locally; do not export unofficial letters
to Drive. Display pending exports and offline sync honestly.

**BR-011** Every version captures metadata, body, template revision, render
settings, source hash, and creator. Regenerating an existing PDF may not
overwrite it. A signature application creates a new version referencing the
same source snapshot and its own PDF; subsequent edits create unsigned versions.

**BR-012** Finalize freezes a selected ready version as a sendable PDF. A
signature is optional for documents to be signed on paper. A signed PDF can be
finalized immediately after owner-authenticated rendering. Edits to the working
draft never change that PDF. No history browsing screen is needed, but version
records and content are mandatory.

**BR-013** In a shared document, active participants may edit the working draft.
The creator manages participants; the administrator may manage retained
documents after deactivation. Signing applies only the acting user's signature.
Removing a participant terminates their live session and API access.

## AI and Contacts

**BR-014** Suggestions are proposals bound to an exact source hash. Applying
one requires user action and matching original text. Reject stale suggestions
and offer a new analysis. No AI response silently modifies the document,
allocates identifiers, applies signatures, changes access, or sends email.

**BR-015** AI may suggest grammar, style, reference, academic type/topic, or a
recipient role. Do not claim factual correction. Users edit system-prompt
inputs through document content; there is no raw prompt-writing UI.

**BR-016** Send the provider only a redacted necessary body and controlled task
instructions. Exclude sender identity, recipient identity/contact details,
signature assets, template content, OAuth tokens, and full Markdown front
matter. Role search executes locally; provider tools never return real contact
records. If redaction cannot confidently remove identifiers, decline the
external request and keep editing available. See `security.md`.

**BR-017** Active users search and maintain a shared institutional recipient
directory. Completing a new recipient offers an inline Save contact action;
do not save incomplete or AI-generated suggestions automatically. Matching is
first structured by role/career/institution, then text, then semantic ranking
if needed. A match requires user confirmation. Handle name/email duplicates.

## Storage and Delivery

**BR-018** Primary archive is the configured organization Drive root, with
MongoDB storing application metadata and durable jobs. Do not delete archived
Drive documents from this application, including after account deactivation.

**BR-019** Archive under `<YEAR>/letters/events/<EVENT>/<TOPIC>/` for an event,
or `<YEAR>/letters/<TOPIC>/` without one. Use the identifier year. Topics include
`classrooms`, `furniture`, `requests`, `invitations`, `notifications`,
`permissions`, `presentations`, and `activities`. `miscellaneous` is a final
fallback requiring explicit confirmation. Event IDs remain stable on rename.

**BR-020** Export names are `<IDENTIFIER>-v<NNNN>.md` and
`<IDENTIFIER>-v<NNNN>.pdf`. Keep separate source/PDF hashes. Existing archived
files are never overwritten; changed archive placement applies to new versions.

**BR-021** The sender chooses an authorized personal Gmail account or the
institutional account. All active users may use the configured institutional
sender; only the administrator connects or disconnects it. This is the
proposed MVP policy, explicit in `decisions.md`.

**BR-022** Sending requires a selected finalized, archived PDF, nonempty valid
To addresses, an editable subject/body, and explicit confirmation. CC and BCC
are optional. Never attach Markdown. Do not infer or add destinations from AI.

**BR-023** Do not duplicate Gmail's message-content history. Retain only minimal
dispatch state needed to prevent duplicate actions and expose unknown outcomes.
After a network timeout during Gmail send, mark the result `unknown`; never
automatically resend it. Keep editing possible if integrations are unavailable.

## Nonfunctional Expectations

Dates default to the organization's local timezone and Spanish display.
Engineering code, identifiers, paths, logs, tests, and documentation stay in
English. UI can remain Spanish. Use no emojis. Use Bootstrap Icons inline SVG
or direct classes only. All UI work must follow the Impeccable instructions in
`/AGENTS.md`; missing skill access must be reported, never claimed as applied.
JavaScript tooling must use pnpm exclusively, including installs, scripts,
builds, one-off tools, containers, and CI. Python tooling continues to use `uv`.

Proposed resource bounds: 100,000 body characters, ten simultaneous editors per
document, twenty active users locally, 2 MiB signature input, and 1 MiB WebSocket
frames. Measure before widening them. Target draft persistence within ten
seconds, convergence within two seconds on a local network, and preview within
five seconds for a normal three-page letter on the documented test host.
