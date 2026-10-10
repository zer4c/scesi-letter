---
version: 1
slug: "frontend-src-modules-signature-SignatureSettingsPage-jsx"
primary_target: "frontend/src/modules/signature/SignatureSettingsPage.jsx"
related_targets:
  - "frontend/src/modules/signature/signatureEnvelope.js"
  - "frontend/src/styles.css"
---

Scope: owner-only signature encryption, replacement, and password re-wrapping.
Mode: Operate.

UI language: Spanish. Keep all member-facing labels, status messages, validation,
and recovery/privacy copy in Spanish; keep this brief and implementation terms
in English.

Audience and task: an invited SCESI member stores or replaces a handwritten
signature image, understands that only their password can unlock the encrypted
envelope, and changes their password without losing a signature they can still
unlock. The page also communicates the unrecoverable lost-password behavior and
the privacy limits of signatures included in a PDF.

## Direction contract

THESIS: Treat the signature as a private credential the owner is carefully
placing under their own control, not as a decorative profile asset or legal
identity badge.

OWN-WORLD: Extend the existing SCESI Letter workspace: white working surface,
warm-gray surroundings, Onest type, charcoal-violet text, institutional red for
primary actions, restrained lines, visible focus, and no decorative icons.

STORY: Show whether an encrypted signature exists, let the owner upload a PNG
and confirm their password, offer an explicit temporary unlock preview, and
provide a separately labeled password-change flow. Errors and recovery limits
must be plain and non-alarming.

STATE CONTRACT: While loading, announce that signature settings are loading.
Treat a missing envelope response as the empty state; for other load failures,
show an error and a retry action. In the empty state, explain that no signature
is saved and offer the save flow. With an envelope, show its saved status and
offer replacement and password-gated preview. The preview is temporary and has
an explicit lock action. During save, unlock, or password change, disable the
relevant actions and announce progress. Keep validation, wrong-password,
concurrent-update, success, and network-failure feedback visible and recoverable.
Changing a password with a saved signature must first unlock and re-wrap its key
locally; a failed re-wrap leaves both the account password and old envelope
unchanged. A successful change clears the temporary preview and closes other
sessions.

FIRST VIEWPORT: The page title and signature status appear first. The upload or
replacement action and password-change requirements are immediately scannable;
security limitations remain present without competing with the primary task.
On narrow screens, controls stack without horizontal scrolling.

FORM: Accept a static PNG up to 2 MiB and 4 megapixels; normalize it locally to
remove metadata, then encrypt it in a browser worker using the v1 Argon2id
(64 MiB, three iterations) and AES-256-GCM envelope. The server stores the
owner-bound encrypted envelope, not the image plaintext. The account password
is required to unlock it; administrators have no signature-envelope access or
recovery path. If the password is lost, the envelope cannot be restored; after
account recovery, the owner must upload a replacement. Do not imply protection
from malicious server code or altered delivered JavaScript. A signature visible
in a PDF can be seen or extracted by anyone with access to that PDF. No
administrator tools, signing operation, audit history, external image upload,
or legal-validity claims on this page.

VISUAL CONTINUITY: Reuse the authenticated workspace shell, Onest typography,
paper and warm-gray surfaces, charcoal-violet text, institutional-red actions,
rounded controls, visible focus, and fine separators. The narrow recovery and
privacy callout is a surface-specific caution treatment, not a new system-wide
semantic color or redesign direction. Keep controls stacked and readable on
small screens without horizontal scrolling.

EVIDENCE: `frontend/.impeccable/review/signature-settings-empty-desktop.png`
captures the no-signature state; `frontend/.impeccable/review/signature-settings-desktop.png`
captures the saved-signature state; and
`frontend/.impeccable/review/signature-settings-mobile.png` captures the saved
state at 390px after password-change feedback. These captures do not stand in
for checking loading, failure, wrong-password, unlock-preview, and conflict
states.

FINISH: inspect the three captures above and verify keyboard labels/focus,
loading/error/empty/existing-signature states, temporary preview lock/unlock,
password-change and re-wrap behavior, feedback and recovery limits, no
horizontal overflow at 390px, browser Argon2id timing, and production build.
The Impeccable CLI is available locally under
`vendor/impeccable/skill/scripts/`.
