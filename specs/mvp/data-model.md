# Data Model and Invariants

Use Beanie documents and Pydantic request/response schemas. Beanie alone does
not guarantee uniqueness, access control, or concurrency safety. Create MongoDB
indexes explicitly and verify them at startup. Store all timestamps in UTC;
display and derive the organization year using `America/La_Paz`.

IDs are opaque UUID strings at the API boundary. MongoDB `_id` is internal.
Never expose password hashes, token ciphertext, signature envelopes belonging to
others, invitation hashes, or storage filesystem paths in general API responses.

## Collections

| Collection | Required fields | Indexes / constraints |
|---|---|---|
| users | id, normalized_email, display_name, password_hash, role, active, revision, credential_revision, created_at | Unique normalized email; unique partial index on role `admin`; credential revision compare-and-swap for signature/password writes |
| invitations | id, token_hash, intended_email, expires_at, redeemed_at, created_by | Unique token hash; one-time redemption in transaction |
| sessions | id, token_hash, user_id, csrf_token_hash, expires_at, idle_expires_at, last_seen_at, revoked_at | Unique token hash; TTL indexes on absolute and idle expiry; authorization checks both directly |
| login_attempts | key_hash, window_start, failures, expires_at | Unique (key_hash, window_start); TTL cleanup; `key_hash` is an HMAC pseudonym, never a raw email or IP |
| signature_envelopes | user_id, envelope_version, kdf, memory_kib, iterations, parallelism, salt, wrapped_dek, wrapping_iv, ciphertext, image_iv, mime, updated_at | Unique user_id; protocol-v1 bounds, canonical Base64, distinct nonces, and ciphertext size validated |
| signing_authorizations | token_hash, user_id, credential_revision, document_id, version_id, source_hash, draft_revision, expires_at, consumed_at? | Unique token hash; consume once atomically; 60-second expiry checked directly; credential changes invalidate; TTL removes expired security state |
| templates | template_id, revision, active, settings, created_by, created_at | Unique (template_id, revision); unique active revision per template ID; immutable revisions |
| contacts | id, name, role_key, role_label, institution, career, emails, active, revision, created_by | Compound role/institution/career index; unique partial multikey normalized-email index |
| events | id, slug, name, year, created_by | Unique (year, slug); slug immutable |
| documents | id, owner_id, participant_ids, identifier?, type, identifier_year?, current_version?, draft_revision, created_at | Unique identifier when set; owner/participants indexes |
| document_states | document_id, crdt_snapshot, state_vector, server_revision, checkpoint_hash | Unique document_id |
| collaboration_updates | document_id, sequence, binary_update, created_at | Unique (document_id, sequence); compact only after durable snapshot |
| document_versions | id, document_id, version_number, metadata_snapshot, body_snapshot, template_revision, source_hash, md_hash?, pdf_hash?, signature_owner_id?, status, finalized_at?, created_by, created_at | Unique (document_id, version_number); snapshots immutable |
| letter_counters | organization, type, year, value | Unique (organization, type, year) |
| archive_mappings | version_id, root_id, folder_ids, md_file_id?, pdf_file_id?, md_hash?, pdf_hash?, status | Unique version_id |
| integration_connections | id, kind, owner_user_id?, mode, google_account, encrypted_tokens{key_id,nonce,ciphertext}, scopes, status, root_folder_id?, expires_at | Unique (kind, mode, owner_user_id); AES-GCM credentials bound to connection identity |
| oauth_states | state_hash, user_id, kind, mode, scopes, encrypted_code_verifier, expires_at, used_at | Unique state hash; PKCE verifier encrypted; user-bound single use and direct expiry check |
| suggestions | id, document_id, source_hash, kind, original?, replacement?, field?, start?, end?, reason, status, created_at | Scoped to document; explicit acceptance, no implicit edits |
| jobs | id, kind, version_id?, user_id?, connection_id?, idempotency_key, status, attempt, lease_until?, next_attempt_at?, error_code?, encrypted_payload? | Unique (user_id, kind, idempotency_key); index status/lease |
| llm_quota_groups | group_key, configured_limits, observed_header_caps?, revision, updated_at | Unique group_key; serialized compare-and-swap/transaction updates for one organization's verified model quota pool |
| llm_quota_reservations | id, group_key, analysis_id, attempt, reserved_input, reserved_output, reserved_at, status, actual_usage?, expires_at | Unique (analysis_id, attempt); group/time index; retain at least 24-hour accounting before TTL cleanup; no prompt/body/contact data |

Do not implement signature-use audit history. Domain authorization and short-lived
one-use signing challenges are required security state, not an audit feature.
Mail jobs retain minimal outcome metadata without keeping full message history.

## Canonical Metadata

Canonical source metadata includes `identifier`, `document_type`, `date`,
`reference`, `salutation`, `recipient_contact_id`, a recipient snapshot (`name`,
`role`, `institution`, `career`, optional email), a sender snapshot, `event_id`,
`topic`, `signoff`, and `template_revision`.

A contact edit changes future selections; existing document snapshots retain
their values unless a participant explicitly applies updated contact data.
Configuration includes a date format in Spanish, optional city, footer
telephone list, URL, contact email, address, and QR destination.

Serialize front matter using a safe YAML library. A saved `.md` must contain
enough metadata to reproduce its layout with the matching template revision.
It contains no signature image, encryption data, or provider credentials.
Importing Markdown validates known fields and rejects unsafe directives.

## State Machines

Document identity: `unnumbered -> numbered`; never reverse or reassign.

Version artifact state: `queued -> rendering -> ready -> archived`, with
recoverable `render_failed` or `sync_failed` states. `finalized_at` may be set
only on a ready, integrity-checked artifact. Finalization does not alter bytes.
Sending requires `archived` plus `finalized_at`.

Unnumbered drafts retain immutable source checkpoints without artifact jobs.
The artifact state machine starts only after numbering. A worker cannot upload
an unnumbered checkpoint or infer a document identifier itself.

Job state: `queued -> running -> succeeded | retry_wait | failed | unknown`.
Expired leases may be reclaimed only for idempotent work. Mail jobs in `running`
with an uncertain upstream side effect become `unknown`, not `queued`.

Suggestion state: `proposed -> accepted | rejected | stale`. Applying a suggestion
uses an expected source hash and creates a normal document change. A suggestion
cannot be accepted twice or applied against an incompatible revision.

## Atomic Operations

- Redeem an invitation and create its user within one transaction.
- Enforce login limits in fixed 15-minute windows: at most five failed attempts
  per normalized account and thirty per network address. Persist only HMAC
  pseudonyms made with the deployment rate-limit key; return `Retry-After` when
  blocked. Limit records are security state, not an audit log.
- Allocate a counter, assign the identifier, create the first numbered snapshot,
  and enqueue export within one transaction. Concurrent saves of the same draft
  reuse the already assigned identifier. Abort transactions leave no assignment.
- Increment a document's version counter and store snapshot/job atomically.
- Change role to admin under the unique partial index. Demoting the only admin
  requires an atomic transfer to an active account. Reject concurrent transfers.
- Update a contact using its expected revision; return a conflict on stale writes.
- Finalize a version with a source/artifact integrity check and authorized actor.
- Enqueue dispatch using a unique idempotency key and selected immutable PDF hash.
- Reserve every LLM attempt under a quota-group revision lock/transaction before
  contacting Groq. Sum active reservations over rolling minute/24-hour windows
  for conservative RPM/RPD/TPM/TPD and any configured ITPM/OTPM limits. A failed
  transaction issues no call. Completion can reconcile proven usage/cache data;
  an uncertain timeout keeps its reservation until the accounting window expires.
  Provider headers can tighten allowances, never overwrite concurrent reservations
  or allow an older response to increase available capacity. TTL is cleanup, not
  the authorization clock. Separate users/API keys cannot create separate pools
  for the same organization/model. Verify provider pool sharing in T00.

## Artifact Storage

Private Docker volume `artifact_data` stores exported bytes under opaque document
and version IDs. Client names are display names only and never filesystem paths.
MongoDB stores version metadata and hashes, not base64 copies of all PDFs.
The private volume is the durable local spool/archive replica; Google Drive is
the primary organization archive. Document artifacts are not deleted by the UI.

Preview bytes are transient and may be discarded. Signature plaintext and
OAuth plaintext are never stored in this volume. Use restrictive permissions
and include this volume in backup/restore procedures.

Collaboration snapshots store the Yjs-compatible CRDT binary state and vector.
Each accepted update is appended with a per-document sequence in the same
transaction that advances the durable revision. A room snapshots and compacts
at most every 100 updates; recovery applies the snapshot and every later
sequence, rejecting gaps or a snapshot hash mismatch. A WebSocket update is not
acknowledged to peers until its durable record commits.
