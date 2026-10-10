# Acceptance Scenarios and Release Gates

Use synthetic people, phone placeholders, generated fake signatures, and
controlled test accounts. Do not recover real personal fixtures from old Git
history. Tests must verify behavior and invariants, not mirror implementations.

## Acceptance Matrix

| Case | Rule(s) | Scenario and required result | Tasks |
|---|---|---|---|
| AC-01 | BR-001, SEC-001..004 | Valid invitation creates a user once; expired/reused/concurrently redeemed invitations cannot create extra users or an admin. | T03 |
| AC-02 | BR-002, SEC-003 | Concurrent administrator promotions leave at most one admin; the last admin cannot disappear without an atomic transfer. | T02, T04 |
| AC-03 | BR-003, SEC-002 | Deactivation revokes HTTP/WS/session access while documents, versions, Drive files, and active participants' access remain intact. | T04, T10, T16 |
| AC-04 | BR-004, SEC-005 | User B and admin cannot fetch/replace/apply user A's signature; DB contains ciphertext, not image plaintext. | T13, T14 |
| AC-05 | BR-005, SEC-014 | New letter always uses the one template; footer phones/URL/QR change through typed settings; no personal telephone is baked into fixtures. | T06, T23 |
| AC-06 | BR-006 | Markdown round-trips safe front matter, Spanish accents, lists/data blocks/page breaks and generates a valid multipage PDF. No DOCX output. | T07 |
| AC-07 | BR-007/008 | Fifty parallel first-save requests allocate unique per-type/year identifiers; repeated same-document saves reuse its code; autosave allocates none. | T08 |
| AC-08 | BR-007/008 | December/January allocation follows La Paz year; type/year counters are independent; sequence 1000 formats without truncation. | T08 |
| AC-09 | BR-008 | Changing date/topic does not change code; changing locked type is rejected by API and collaborative metadata validation. | T08, T10 |
| AC-10 | BR-009/010 | Multiple keystrokes create a bounded checkpoint; unchanged Save creates no extra version; numbered checkpoints queue MD/PDF without approval. | T08..T12 |
| AC-11 | BR-011/012 | Edit or signature application creates a new version; hashes/bytes of earlier source and PDF remain unchanged; unsigned finalization is supported. | T08, T09, T14 |
| AC-12 | BR-013 | Two browsers make concurrent body and field edits, converge, and recover acknowledged edits after disconnect/backend restart. | T10, T12 |
| AC-13 | BR-013, SEC-003 | Unauthorized room/document/artifact access fails; removing a participant prevents new edits and closes the active room. | T08, T10 |
| AC-14 | BR-014 | Accept changes only the exact matching source range/field; stale suggestion, double accept, or a collaborator edit causes a safe conflict. | T17, T18 |
| AC-15 | BR-015 | Grammar/style/REF/type suggestions are structured and optional; no unaccepted AI output changes source, code, contacts, signatures, or mail. | T17, T18 |
| AC-16 | BR-016, SEC-010/011 | A spy provider/tool transport receives no synthetic sender/recipient names, phones, emails, signature, front matter, template, or OAuth secrets. Unresolved name detection blocks transmission. | T17 |
| AC-17 | SEC-011 | Prompt injection asking for mail/Drive writes or credentials cannot grant tools or reveal data; malformed JSON/schema is rejected. | T17 |
| AC-18 | BR-017 | Role search uses career/institution; ambiguity requires a choice; quick edit uses expected revision and does not silently rewrite old letters. | T05, T19 |
| AC-19 | BR-018/019 | Event/non-event classroom/furniture letters go to correct stable year/topic folders; miscellaneous needs confirmation; event rename retains identity. | T08, T16 |
| AC-20 | BR-020 | Both version-named files exist in real Drive; partial upload retry reconciles and does not overwrite/create duplicate artifacts. | T16 |
| AC-21 | BR-021/022 | Real personal and institutional sender flows deliver the selected archived/finalized PDF to controlled To/CC/BCC accounts; no Markdown attached. | T21, T22 |
| AC-22 | BR-023 | Double click/same idempotency key sends once; timeout after upstream submission yields unknown and never automatic resend. | T21, T22 |
| AC-23 | SEC-005/009 | Wrong password, altered ciphertext/AAD, and reused nonce fixture fail; known-password change re-wraps; forgotten password cannot decrypt old image. | T13 |
| AC-24 | SEC-006/007 | Signing token bound to user/source expires and is single-use; stale source rejects; no signature plaintext in DB/files/job payloads/logs. | T14 |
| AC-25 | SEC-008 | An authorized final PDF shows the signature; product explains published-image access without claiming legal signing or zero knowledge. | T14, T22 |
| AC-26 | SEC-012/013 | OAuth state replay/wrong user/expiry fails; encrypted tokens cannot be read without server key; personal tokens never exposed to admin/browser. | T15 |
| AC-27 | SEC-014 | Unsafe YAML/HTML, external image fetching, malicious paths, image bombs, excessive input and forged MIME are rejected. | T06, T07, T13 |
| AC-28 | SEC-015 | BCC/message/signature/private provider content is absent from SSE/WS/shared job views and redacted logs. | T10, T14, T17, T21 |
| AC-29 | BR-010, jobs | Restart DB/backend/worker during save/upload; durable idempotent work resumes without duplicate versions/exports; acknowledged edits survive. | T09, T10, T16 |
| AC-30 | Integrations | Revoke Google token or return Groq 429/timeout; show recoverable status, keep manual editing/preview/save available, honor bounded budgets. | T15..T18 |
| AC-31 | UI contract | Full edit/sign/send/contact flow works keyboard-only, at 200% zoom, on narrow screens, and without external logo loading. | T11..T23 |
| AC-32 | P-01 | Verify Free plan/account eligibility for the candidate with a real local-tool round trip and schema-validated Spanish suggestion; record actual limits/date and resolve pasted table attribution; no paid fallback. | T00, T17 |
| AC-33 | P-02, BR-005 | Approved original assets render matching repeated header/footer without baked telephone numbers; use generic fixtures until approved assets available. | T06, T07 |
| AC-34 | P-05 | Google Other Contacts import uses the personal contacts.other.readonly scope, paginates previews, imports only selected records after confirmation, skips duplicate emails, and never reads Gmail messages. | T20 |
| AC-35 | Local runtime | Clean setup and backup restore preserve MongoDB/version/artifact hashes; env secrets absent from image layers/browser bundle/Git; bootstrap remains idempotent. | T01, T24 |
| AC-36 | AGENTS.md | All work uses focused branches, atomic <=50-character English subjects, English engineering paths/code, no emojis, Bootstrap Icons, modular domains. | all |
| AC-37 | AGENTS.md, tooling | One pinned pnpm version and `pnpm-lock.yaml`; frozen clean install/build and Docker/CI use only pnpm; no forbidden package-manager invocation remains. | T01, T25 |
| AC-38 | Provider contract | Concurrent users share durable RPM/RPD/TPM/TPD reservations; headers mean RPD/TPM; split limits/cache/429/reset durations are handled safely; GPT-OSS uses serial tools and supported reasoning/JSON parameters. | T00, T17 |
| AC-39 | Impeccable | Codex discovers the pinned skills installed with pnpm; reviewed English `PRODUCT.md`/`DESIGN.md` guide UI tasks; accessibility/responsive audit findings are resolved or explicitly reviewed. | T11..T23, T25 |

## Required Test Layers

- Unit checks: taxonomy, normalization, redaction, YAML, path building,
  envelope/protocol validation, MIME formatting, suggestion offsets.
- Real MongoDB integration: transactions, counter races, unique admin,
  versioning, session expiry, leases, and backup/restart persistence.
- Contract checks: request/response schemas, IDOR, CSRF, stale hashes,
  scoped events, OAuth state and no secret serialization.
- Browser checks: two-user collaboration, signature crypto round trip,
  stale preview/suggestions, accessibility and sending confirmation.
- Controlled live provider checks: OAuth connect/refresh, Drive pair upload,
  Gmail delivery and BCC, current Groq model/tool/quota behavior.

No external test may send real letters or disclose private contacts. Use test
accounts and an explicitly approved test send. A fake transport cannot satisfy
AC-20, AC-21, or AC-32.

## End-to-End Release Scenario

1. Start local Compose from a clean checkout using safe local secrets.
2. Bootstrap the administrator once; invite two synthetic member accounts.
3. Configure the default template and Drive; connect institutional/personal Gmail.
4. Member A creates an unnumbered classroom request and adds member B.
5. Both edit concurrently; verify metadata/body convergence and a reconnect.
6. Save, receive `SOL-SCESI-<YEAR>-001`, and archive its MD/PDF pair.
7. Analyze a sanitized body, accept one suggestion, reject another, and trigger
   a stale suggestion by editing from the other browser.
8. Member A unlocks their synthetic signature, produces a new finalized PDF,
   and verifies B/admin cannot apply that reusable envelope.
9. Send the selected archived PDF personally with CC/BCC; then exercise a
   separately confirmed institutional sender test. Check real attachments.
10. Edit the draft again; old archived/sent PDF hashes remain unchanged.
11. Disable member A; document remains available to B and the administrator.
12. Restore a backup in a clean local environment and verify artifacts/metadata.

## Evidence and Completion

Record test target, versions, current run date, passed/failed/skipped/unrun counts,
provider accounts by non-sensitive labels, and relevant hash/convergence results.
Do not commit recipient addresses, keys, signatures, full raw responses, or tokens.
Track evidence in review descriptions or safe verification notes.

A local editor-only milestone is useful but not the requested full MVP. Missing
assets, OAuth credentials, tool-capable free model verification, Impeccable access,
or collaboration correctness remain explicit prerequisites until resolved.

Version history UI and simultaneous multiple signatures are deferred; immutable
version persistence and a single owner signature are required now.
