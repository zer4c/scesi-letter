# Decisions and Prerequisites

## Confirmed Product Decisions

The user approved React, FastAPI/Python with `uv`, a modular monolith, MongoDB,
Pydantic-compatible documents, invitation-only accounts, at most one admin,
collaboration in the MVP, one default template, one owner-controlled signature,
password-dependent encryption with no recovery, Markdown/PDF pairs, annual
per-type numbering, permanent documents, Drive organization, human approval of
AI suggestions, both Gmail sender modes, CC/BCC, and local deployment first.

Multiple signatures and advanced history UI are deferred. A scanned signature
has no claimed legal cryptographic validity. Retained PDF versions are immutable.

## Proposed Engineering Decisions

These choices make implementation concrete. They are assumptions for review,
not decisions previously made by the user.

| ID | Decision | Reason / consequence |
|---|---|---|
| D-01 | Beanie with Pydantic and PyMongo Async | Typed documents; database indexes still enforce races. Verify compatible pinned releases. |
| D-02 | Single-node MongoDB replica set locally | Supports transactions for version/counter/job invariants. |
| D-03 | Yjs with CodeMirror 6 and Python `pycrdt` | Concurrent editing with recovery; prove binary interop before editor work. |
| D-04 | Existing fpdf2 engine approach, reimplemented safely | Bundled fonts and Markdown-driven academic layout; no old-history restoration. |
| D-05 | Plain Markdown body plus structured fields | Document editor is not a general YAML/code execution surface. |
| D-06 | Shared recipient directory for active members | Useful academic role lookup; source data stays local. |
| D-07 | All active users may send institutionally | Visible choice, explicit confirmation, no arbitrary From address. |
| D-08 | Institutional Drive archive for all documents | Organization retains files independently of an individual's account. |
| D-09 | Number only on first explicit Save | Avoid autosave exhausting identifiers. |
| D-10 | Persistent snapshots at bounded debounce | Implements versioned modifications without a PDF for every keystroke. |
| D-11 | Browser-owned signature decryption | Server stores only envelopes; plaintext is transient during PDF generation. |
| D-12 | One worker using MongoDB durable jobs | No Redis/Celery required for the local MVP. Worker is the same monolith codebase. |
| D-13 | Google Contacts import via People API | Avoid reading complete Gmail mailboxes. See open scope question below. |
| D-14 | Fail closed on uncertain AI redaction | Privacy constraint takes precedence over optional suggestions. |
| D-15 | Start evaluation with `openai/gpt-oss-20b` | Supplied official docs list production status, local tools, JSON mode, and a 131,072-token context; free-tier eligibility remains unverified. |

The user requires pnpm exclusively for all JavaScript tooling. This overrides
legacy commands and lockfiles in the current scaffold and all external installer
examples. It is a confirmed rule, not a proposed default.

## Open Prerequisites

| ID | Prerequisite | What can continue | What cannot be called complete |
|---|---|---|---|
| P-01 | Verify account access/plan/quotas, resolve supplied rate-table plan-label conflict, check retention and live tool/schema behavior | Local graph, documented capabilities and numeric table, fake provider | Real provider readiness / certified Free entitlement |
| P-02 | Obtain usable original PNG assets through normal attachments | Generic public-style fixture rendering | Exact approved template fidelity |
| P-04 | Configure Google OAuth project and two sender connections | Mocked adapters / errors | Real Drive/Gmail integration |
| P-05 | Choose registered Google Contacts import versus extracting correspondents from Gmail | Manual contacts, role matching | Gmail mailbox contact extraction |

For P-05, prefer People API contacts in the MVP. Extracting correspondents from
Gmail would require broader mailbox scopes and a separate explicit decision;
do not silently add mailbox read access. Keep the contact import UI disabled
until its approved source is known. P-05 does not remove sending from the MVP.

## Template Assets Exception

The user explicitly permits the supplied public SCESI/UMSS logos and header/footer
design. The approved email logo URL is `https://i.imgur.com/npTbdR8.png`.
Telephone numbers must be runtime configuration, never embedded in committed
fixtures. Footer URL, email, QR target, and address are editable settings.

The supplied footer PNG contains telephone text. Rebuild its layout using
editable text and a generated QR; do not commit the unredacted complete footer
or use it as a fixed background. Store separately usable public logos in
`resources/images/` after checking their provenance. Preserve attribution.
No personal signature asset is a permitted repository exception.

## Research Status

T11 resolved the Impeccable setup prerequisite for Codex: version 4.5.2 is
pinned by the official `vendor/impeccable` submodule and linked into the project
skill directory. `PRODUCT.md` and the shipped-surface design record are present.
The one required mechanical detector invocation could not launch its internal
Chromium; the user accepted integrating T11 with that validation limitation
recorded. The broader product visual direction remains open for the user's
manual refinement.

Attempts to fetch official Groq models, rate limits, tool-use documentation,
Google OAuth/scope documentation, and Impeccable's tutorial on 2026-10-10
returned HTTP 403 in this environment. An escalated retry of the Groq quota
page also returned 403. The user subsequently supplied official Tool Use,
Supported Models, Local Tool Calling, Reasoning, and Rate Limits text, plus the
Impeccable getting-started tutorial. These establish documented capabilities,
numeric quota-table values, and the design workflow. The latest pasted rate
table has contradictory plan labeling; actual Free entitlements/account access
remain unverified.
See `provider-notes.md` for provenance, model choice, and documentation conflicts.

The current repository has a demonstration automation endpoint that returns
`completed` without actually notifying, creating a report, or calling a webhook.
Replace this behavior within task T17; it is not an implemented MVP workflow.
