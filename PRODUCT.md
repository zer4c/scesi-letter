# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

Invited SCESI members who prepare academic correspondence, including requests for
classrooms or furniture and invitations. An administrator manages membership
and shared organization settings, but cannot access another member's signature.

## Product Purpose

SCESI Letter helps members create academic letters from a default template,
collaborate on Markdown, preview and preserve versioned PDFs, and optionally
sign, organize, and send a selected PDF. Success means completing this workflow
with fewer repetitive steps while keeping the editable source and resulting
document aligned.

## Positioning

An academic correspondence workspace that connects structured letter fields,
collaborative Markdown, and versioned PDF output with member-controlled
signatures and organization-aware delivery.

## Operating Context

Members work in Spanish and may collaborate on the same letter. The editor
combines structured fields and Markdown with a PDF preview; on small screens,
editing and preview use separate tabs. Letters are used in a university setting
and may be printed, emailed, or signed in person. Generated correspondence has
no asserted legal validity.

## Capabilities and Constraints

- The MVP uses one default academic template. Its supplied header and footer
  style must be preserved; configurable phone numbers, URLs, and QR content are
  not personal data to hard-code into the application.
- Markdown remains editable and is retained with versioned PDF output. DOCX is
  out of scope. Documents are not deleted through the application.
- The first explicit save assigns a deterministic academic identifier. The
  exact nomenclature follows the product specification; identifiers are locked
  after assignment. Changes produce new versions.
- A member's signature image is encrypted for that member and unlocked with
  their password for an individual signing operation. Lost-password recovery
  for the signature is intentionally unavailable. Administrators cannot
  inspect other members' signature material.
- Invitations control registration. There are ordinary members and at most one
  administrator; no reader role is planned.
- Recipient suggestions and contact updates assist the author but do not
  silently rewrite existing correspondence. AI suggestions require individual
  human review. Provider use must respect the documented privacy boundary and
  organization-wide quotas.
- Gmail can send a selected PDF with a short message and optional CC/BCC. The
  Markdown source is never attached. Personal and configurable institutional
  sender accounts are supported. Google Drive organization is year-first,
  followed by event and topic where applicable; deletion is left to Drive
  administrators.
- The MVP is intended to run locally. Deployment to a VPS is undecided.
- The UI is Spanish; implementation, identifiers, and technical documentation
  are English. Use Bootstrap Icons only, and do not use emojis.

## Brand Commitments

Preserve the supplied SCESI and UMSS marks and the academic letter header/footer
when producing correspondence. The approved public SCESI logo URL for email is
`https://i.imgur.com/npTbdR8.png`. Phone numbers in the document footer must be
configurable rather than treated as fixed application copy.

## Evidence on Hand

The repository's `specs/mvp/` contains the requirements, architecture, UI,
security, integration, provider, API, data-model, and acceptance specifications.
The user supplied reference images for the academic page header/footer and
institutional marks in the conversation. No additional private assets or
credentials are part of the product record.

## Product Principles

- Keep the authored Markdown and the PDF preview in sync.
- Make saved state, collaboration, numbering, and delivery status explicit.
- Keep signatures private to their owner, including from administrators.
- Treat AI output as reviewable suggestions, never silent edits.
- Minimize repetitive actions without hiding consequential choices.

## Accessibility & Inclusion

Core workflows must support keyboard-only operation, visible focus, accessible
names and labels, announced status changes, adequate contrast, 200% zoom,
reduced motion, usable touch targets, and a responsive narrow-screen layout.
