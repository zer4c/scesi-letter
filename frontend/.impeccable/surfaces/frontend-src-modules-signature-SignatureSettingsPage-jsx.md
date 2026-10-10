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

FIRST VIEWPORT: The page title and signature status appear first. The upload or
replacement action and password-change requirements are immediately scannable;
security limitations remain present without competing with the primary task.
On narrow screens, controls stack without horizontal scrolling.

FORM: Browser-side Argon2id/AES-GCM envelope v1 only. No administrator tools,
public signing operation, audit history, external image upload, or legal claims.

FINISH: inspect desktop and 390px screenshots, keyboard labels and feedback,
loading/error/empty/existing-signature states, no horizontal overflow, browser
Argon2id timing, and production build. The Impeccable CLI is available locally
under `vendor/impeccable/skill/scripts/`.
