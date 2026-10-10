# UI Behavior and Design Contract

Read the actual Impeccable skill/tutorial referenced by `/AGENTS.md` before UI
implementation. Apply its accessible layout, typography, spacing, and state
guidance without changing the supplied academic PDF style. UI copy is Spanish;
component names, CSS identifiers, hooks, and tests are English. No emojis.
Bootstrap Icons only, inline SVG or direct class. Icon-only controls need an
accessible name and visible keyboard focus.

Follow the supplied installation/context/review procedure in `provider-notes.md`
using pnpm only. Review `PRODUCT.md` and `DESIGN.md` before each UI task. Record
actual Impeccable skill discovery and audit results; a tutorial link alone does
not demonstrate that the skill was installed or used.

## Main Routes

- `/login`, `/invite/:token`: authentication and invitation redemption.
- `/documents`: personal/shared documents with sync/finalization status.
- `/documents/:id`: collaborative editing workspace.
- `/settings/signature`: own encrypted signature upload/replacement.
- `/settings/connections`: own Google accounts and connection status.
- `/settings/organization`: admin-only members, template, Drive, institutional Gmail.

## Document Workspace

Desktop: structured fields and Markdown editor on the left, PDF preview on the
right. Top controls show identifier or unnumbered status, save state, participants,
and Save. A compact secondary toolbar contains Analyze, Sign, Finalize, and Send.
Disable controls with an explanatory state when their prerequisites are missing.

On small screens use Edit/Preview tabs without losing the current draft. Never
try to fit the desktop PDF width into a narrow unreadable panel. Track revision
on every preview request and display only the newest matching response.

The default template is automatic. Fields: type (locked after numbering), date,
reference, recipient, role/career/institution, optional event, topic, and signoff.
The structured fields remain synchronized during collaboration. Avoid a second
unsynchronized form state. A preview failure leaves the editor usable.

## Contacts

Recipient field has an autocomplete list, role/institution hints, and an inline
Bootstrap pencil action. Selecting a contact copies a snapshot; editing opens
a focused accessible popover/dialog, then returns focus to the field. New
recipients can be saved in place after confirmation. An ambiguous role shows
multiple candidates, never auto-selects the first. Contact directory changes do
not silently rewrite existing letters.

## AI Suggestions

Suggestions appear as text-editor annotations or a collapsible side panel with
original/replacement, reason, Accept, and Reject. Support individual decisions;
no unconditional Apply all in the MVP. Show the privacy-filtered input before
the first provider use or when uncertain identifiers require user redaction.

Reference and recipient-role suggestions populate proposals, not final fields.
If collaborators edit the source, mark incompatible proposals stale. A provider
quota/error state must leave manual editing, Save, preview, and Gmail available.

## Signature

Signature settings show only the owner's slot and encrypted-storage status.
Provide upload/replace and clearly explain unrecoverability after password loss.
Do not display another user's envelope through admin settings.

Sign opens a password prompt for that operation, identifies the exact PDF/source
being signed, and applies the fixed slot. If the source changes during unlock,
reject that request and ask for a new selected version. Clear password and
temporary image references on completion, cancel, or navigation. Signature
preview before application is private to the owner; the published PDF is shared
according to document/Drive access.

## Save, Archive, and Finalization

Distinguish `changes pending`, `saved locally`, `rendering`, `sync pending`,
`archived`, and `finalized`. Save requires no approval modal. The first explicit
Save assigns the deterministic identifier. Repeated unchanged saves do not
consume a number or add a version.

After finalization, edits continue in a new unsigned version. Always identify
which finalized version will be sent. Offer downloads and Drive access links,
but no Delete document control. A synchronization failure has a Retry action.

## Gmail Composer

Show sender selector with verified personal/institutional account addresses,
To, expandable CC/BCC, subject, short editable body, and the one selected PDF.
PDF version/identifier is visible. Markdown is never attached. The institutional
logo may use the user-approved URL; external mail clients may block its display.

Use safe MIME generation, with plain text and optional controlled HTML.
Escape body content; do not treat arbitrary editor text as email HTML. Final
Send requires explicit confirmation of addresses, sender, and attachment.
Prevent double-click dispatch while pending. For `unknown` outcome, instruct the
sender to check Gmail before any explicit new send; do not claim success/failure.

## Collaboration and Accessibility

Show participant presence, connection status, reconnecting state, and unsaved
changes. Do not imply awareness cursors are persisted history. Membership
revocation closes editing promptly with a clear explanation.

Required checks: labels, keyboard-only editing/actions/dialogs, proper dialog
focus/escape handling, status announcements, AA contrast, 200% zoom, touch targets,
reduced motion, and usable mobile layout. PDF preview must have a fallback
download if embedded viewing is unsupported. Core workflows must remain usable
without decorative icons or external logo loading.
