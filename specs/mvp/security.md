# Security and Privacy Contract

## Authentication and Membership

**SEC-001** Use Argon2id for server-side password hashing with independent salts.
Benchmark parameters and pin the implementation. Accept passphrases, require
at least twelve characters, support password managers, and never log passwords.
Rate-limit login attempts to five failures per normalized account and thirty
per network address in a fixed fifteen-minute window. Return `Retry-After` on
block. Store only HMAC-SHA-256 pseudonyms using a deployment secret, never raw
email addresses or IPs, and expire buckets with a TTL index.

**SEC-002** Use opaque server sessions in HttpOnly, SameSite cookies. Use Secure
cookies under HTTPS. A development-only HTTP cookie mode must be explicit in
configuration and reject non-loopback/public origins. Protect mutation endpoints
with CSRF validation and verify WebSocket Origin. OAuth callbacks validate
session/state and exact registered redirect binding; top-level callbacks may
have no Origin header, so do not depend on that header alone. Store session hashes.
Use a thirty-minute idle expiry and twelve-hour absolute expiry, refreshing the
idle window at most every five minutes. Mutations require the `X-CSRF-Token`
header to match the session-bound CSRF cookie. Reauthenticate for sensitive
actions. Disabling a user revokes sessions and connected rooms.

**SEC-003** Administrator powers cover membership, template settings, and
institutional integrations. They do not confer signature-envelope access.
Every request authorizes the current actor and target; opaque IDs are not access
control. Invitations expire after 72 hours by default and cannot be reused.
Membership changes require the expected user revision. Promoting a user to
administrator atomically transfers the singleton role; the former administrator
is demoted. The last active administrator cannot be deactivated or demoted.
Deactivation revokes that user's sessions and retains their documents and files.

**SEC-004** Bootstrap the administrator only if none exists. Read initial
credentials from deployment configuration; never reset an existing admin's
password at each startup. Remove bootstrap credentials after initial setup.
Password recovery cannot decrypt a previous signature. The MVP may require
admin-issued reset invitations; reset revokes sessions and marks the old envelope
unusable pending owner replacement.

## Signature Envelope

**SEC-005** Encrypt in the owner's browser. Proposed envelope protocol v1:

1. Validate and normalize one uploaded PNG image, maximum 2 MiB and bounded
   pixel count. Reject SVG, animated images, and MIME spoofing. Remove metadata.
2. Generate a random 256-bit data encryption key (DEK).
3. Derive a key encryption key (KEK) from the current account password using
   Argon2id, an independent random salt, and a maintained browser WASM library.
   Initial baseline: 64 MiB memory, three iterations, one lane; benchmark and
   document supported-device constraints before freezing protocol parameters.
4. Encrypt normalized image bytes using AES-256-GCM with a fresh 96-bit nonce.
5. Wrap the DEK using AES-256-GCM with the KEK and a different nonce.
6. Bind user ID, envelope version, and algorithm identifiers as authenticated
   additional data. Store ciphertext, parameters, salt, and nonces only.

Never implement a custom cipher, reuse an encryption nonce, use the login hash
as an encryption key, or encrypt with a server-global signature key. Validate
KDF bounds on receipt to prevent resource exhaustion. Library interoperability,
wrong-password failure, AAD tampering, and nonce generation are release gates.

Protocol-v1 implementation uses the maintained `hash-wasm` Argon2id library in
a dedicated browser worker and Web Crypto AES-GCM. It fixes the KDF parameters
above, requires distinct 12-byte nonces, binds the owner UUID/version/algorithm/
purpose as AAD, and rejects non-PNG, animated, over-2-MiB, or over-4-megapixel
inputs. PNG data is decoded and redrawn locally to remove metadata before
encryption. The worker is terminated after each operation; explicit buffer
clearing is best effort and does not promise forensic erasure.

Initial browser measurement (2026-10-10): headless Chromium 151.0.7922.173 on
the development Linux environment completed a synthetic 2x2 PNG normalize,
Argon2id+AES-GCM encrypt, and mocked upload in 862 ms; decrypt plus temporary
preview creation took 915 ms. Each Argon2id derivation allocates 64 MiB. These
are single end-to-end desktop-environment observations, not device-class
percentiles. Real mobile hardware and Safari/Firefox remain unverified; do not
claim them as supported until the browser round-trip is run there. The bounded
input and fixed KDF values are enforced before expensive derivation.

Envelope upload and password change use a credential-revision compare-and-swap;
password change also compares the expected envelope timestamp in the same
MongoDB transaction. A stale tab cannot replace a newer envelope or change the
password while re-wrapping an outdated copy.

**SEC-006** Each signing operation requires the owner to enter their password
again. Do not cache an unlocked signature across operations. Reauthenticate the
session and issue a single-use authorization bound to user, document, exact
source hash/version, and a sixty-second expiry. The browser decrypts locally
and submits the image over authenticated TLS to the synchronous signed-render
endpoint. Server checks the bound source and consumes the authorization once.

**SEC-007** Render signature plaintext only in memory during the request. Never
enqueue it in durable jobs, write it to temporary files, traces, dumps, logs, or
Drive as a standalone image. Persist only the resulting authorized PDF plus the
encrypted envelope. Request/response logging must omit bodies on this route.
Browser clear-on-close/operation is best effort; JavaScript memory cannot offer
a guaranteed forensic wipe. Bound payload and renderer execution time.

**SEC-008** A signed finalized PDF contains the signature visually. Any person
allowed to read that PDF, including Drive administrators, can capture/extract it.
The owner-only guarantee protects the reusable envelope and signing workflow,
not signature pixels already published by the owner. A malicious server operator
can observe plaintext during rendering or alter delivered JavaScript; this
architecture does not provide protection against that threat. Do not advertise
zero knowledge, legal validity, or full end-to-end secrecy.

**SEC-009** If the password is forgotten, the encrypted signature is lost. Allow
the owner to upload a replacement after account recovery. No admin backdoor.
A known-password change must decrypt/re-wrap locally before invalidating the
old envelope. Failed re-wrap leaves the old envelope unchanged. Authentication
plus a second password prompt is reauthentication, not two-factor authentication.

## AI Boundary

**SEC-010** Privacy processing happens locally before every provider request.
Use controlled source fields: body only, never full Markdown with front matter.
Detect sender/recipient names and their normalized variants from structured
metadata and contacts; replace emails, phone numbers, identifiers, and recognized
person entities with placeholders. Use local NER or a vetted local classifier
for free-form names. Unknown/unresolved entities require explicit local redaction
or make the request unavailable. Regex alone cannot promise name removal.

Run the same filter on model responses and tool results. Local role-resolution
returns real contacts directly to the frontend, while the provider sees role
keys, allowed classifications, and match counts only. Do not send arbitrary
tool output, names, account addresses, signatures, or template content to Groq.
Store no unredacted prompts in tracing tools; disable LangSmith/external tracing
by default. Keep internal prompts in versioned English source files and ask for
Spanish suggestions with structured schemas.

Keep a local-only redacted-to-source span map. Suggestions cannot cross protected
identity placeholders or reinsert inferred personal data. Validate range/text
alignment before translating offsets; discard uncertain proposals instead of
applying edits to the wrong original range. Never send this map to the provider.

**SEC-011** Model tool access is allowlisted: classification taxonomy and local
role-key lookup only. Tools have typed inputs, bounded results/time, and no
filesystem, internet browsing, email, Drive writes, credential access, signature
access, or code execution. Document text is untrusted data; instructions inside
it cannot override the system prompt or approve side effects.

## Google Tokens and Rendering

**SEC-012** OAuth tokens require encryption under an independently supplied
server key from deployment secrets. Use AES-GCM envelope encryption or a vetted
library; store key ID for rotation. Do not confuse this key with user signature
keys. Database access without the server key must not reveal refresh tokens.
Administrators cannot retrieve personal connection tokens through any endpoint.

**SEC-013** Validate OAuth state, user binding, expected scopes, PKCE where
supported, expiration, and one-time use. Connection completion displays the
actual authorized Google account. Disconnect revokes access where available and
deletes credential material without deleting archived files.

**SEC-014** Parse Markdown/YAML safely. Disable raw HTML and external image
fetching. Fetch only the explicitly approved public email-logo origin if needed;
never fetch arbitrary QR URLs to generate a QR. Render typed internal resources,
with path traversal, SSRF, oversized files, and decompression bombs rejected.

**SEC-015** BCC is private to the sender and transient dispatch processing.
Do not broadcast it to collaborators or store complete message bodies/history.
Keep operational logs redacted, with request/job IDs and error codes only.
There is no signature-use audit UI or permanent audit collection.

## Local Operations

Expose the web interface on loopback by default. Do not expose MongoDB publicly.
Use TLS for provider traffic and any non-loopback deployment. Validate backups
of MongoDB, artifact volume, and integration encryption keys; they must remain
access-controlled. Losing the token-encryption key requires reconnecting Google.
No real phone numbers, keys, passwords, tokens, or signature fixtures go in Git.
