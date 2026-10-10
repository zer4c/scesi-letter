# Local Operations and Recovery

This runbook applies to the local Docker Compose deployment. Compose binds the
application and MongoDB ports to loopback; do not treat the development stack as
a hardened public deployment. Keep `.env`, backup archives, and restored data
outside Git and restrict access to them.

## First setup and provider configuration

Use the steps in [README.md](../README.md) to create `.env`, start Compose, and
bootstrap the first administrator. `.env.example` contains development-only
placeholders, including a known local MongoDB password and fixed signing-key
examples. It is a template, not a secret store or production configuration.
Replace every placeholder before sharing a machine or exposing any service.
The Compose setup passes provider secrets at container runtime; do not add them
to Docker build arguments, images, frontend variables, or committed files.

Generate independent values for `APP_RATE_LIMIT_KEY` and
`AI_PREVIEW_SIGNING_KEY` with `openssl rand -hex 32`; generate
`INTEGRATION_ENCRYPTION_KEY` with `openssl rand -base64 32`. Keep the
integration key and its `INTEGRATION_KEY_ID` stable when restoring encrypted
Google tokens. Losing or replacing that key makes stored provider tokens
unreadable. User signatures are encrypted with each user's password; the
application cannot recover them after that password is forgotten.

Google setup references:

- Create OAuth credentials: <https://console.cloud.google.com/apis/credentials>
- Enable Gmail API: <https://console.cloud.google.com/apis/library/gmail.googleapis.com>
- Enable Drive API: <https://console.cloud.google.com/apis/library/drive.googleapis.com>
- Enable People API: <https://console.cloud.google.com/apis/library/people.googleapis.com>
- Register the exact callback in `.env`:
  `http://localhost:8080/api/integrations/google/callback`
- Groq keys: <https://console.groq.com/keys>
- Groq account/model quotas: <https://console.groq.com/settings/limits>

Keep `LLM_PROVIDER=disabled` unless Groq is deliberately configured. Provider
eligibility and quotas depend on the account; values in `.env.example` are
provisional, not verified entitlements.

## Health and routine inspection

From the repository root:

```bash
docker compose ps
docker compose logs --tail=200 backend worker mongodb
curl --fail http://localhost:8000/api/ready
```

Readiness verifies MongoDB connectivity and persistence initialization. Do not
publish its internal diagnostics or environment values in an issue or log.

## Worker recovery

Export, Drive archive, and mail jobs are persisted in MongoDB. A worker restart
does not delete the job queue. If a worker is unhealthy, first inspect its logs
and the job status through the authenticated API, then restart only the worker:

```bash
docker compose logs --tail=200 worker
docker compose restart worker
docker compose logs --tail=100 worker
```

An expired lease allows eligible export/archive work to be reclaimed. Do not
manually mark a job queued unless its operation is known to be safe and
idempotent. A Gmail dispatch with an unknown outcome is deliberately not
retried automatically: first check the sender account's Sent folder/search for
the identifier and recipients. If delivery cannot be determined, resolve it
with the sender before submitting a new send; the app cannot prove whether
Google accepted a timed-out request.

For an expired Google credential, reconnect the affected personal account as
its owner or the institutional account through organization settings. Do not
delete MongoDB records to force reauthorization. Drive jobs waiting for a
connection can be retried from the document's archive controls after the
connection is restored. Gmail jobs in `unknown` require human reconciliation,
not worker restart.

## Consistent backup

Back up both the MongoDB application database and the artifact volume. Stop the
API and worker first so document metadata and file hashes are quiescent; leave
MongoDB running. The script refuses to run while either service is running.
Choose a restricted absolute path outside this checkout:

```bash
docker compose stop backend worker
./scripts/backup-local.sh /absolute/path/to/restricted-backups
docker compose start backend worker
```

The script creates a new mode-0700 timestamped directory containing a gzip
Mongo archive, a gzip artifact archive, a per-artifact SHA-256 manifest, and
archive checksums. It will not overwrite an existing timestamp directory. Keep
these files private: they contain document source, generated PDFs, recipient
data, and other sensitive records. Encrypt them before copying them off the
machine and store `.env` secrets separately in a password manager or encrypted
secret store. Never commit backups.

## Isolated restore drill

The following restore uses a separate Compose project and therefore separate
named volumes. It does not overwrite the normal project's MongoDB or artifact
volumes. Stop the normal application to free its loopback ports, and identify
the exact backup directory before running these commands:

```bash
docker compose stop
RECOVERY_PROJECT=scesi-recovery
BACKUP_DIR=/absolute/path/to/restricted-backups/scesi-YYYYMMDDTHHMMSSZ
sha256sum --check "$BACKUP_DIR/SHA256SUMS"
docker compose -p "$RECOVERY_PROJECT" --env-file .env up -d mongodb mongo-init
docker compose -p "$RECOVERY_PROJECT" --env-file .env exec -T mongodb bash -ec \
  'mongorestore --username "$MONGO_INITDB_ROOT_USERNAME" --password "$MONGO_INITDB_ROOT_PASSWORD" --authenticationDatabase admin --drop --gzip --archive' \
  < "$BACKUP_DIR/mongodb.archive.gz"
docker compose -p "$RECOVERY_PROJECT" --env-file .env build backend
docker compose -p "$RECOVERY_PROJECT" --env-file .env run --rm --no-deps -T backend \
  tar -C /var/lib/scesi -xzf - < "$BACKUP_DIR/artifacts.tar.gz"
docker compose -p "$RECOVERY_PROJECT" --env-file .env up -d
docker compose -p "$RECOVERY_PROJECT" --env-file .env ps
curl --fail http://localhost:8000/api/ready
umask 077
RECOVERED_MANIFEST="$(mktemp)"
docker compose -p "$RECOVERY_PROJECT" --env-file .env run --rm --no-deps -T backend \
  python -c 'import hashlib; from pathlib import Path; root=Path("/var/lib/scesi/artifacts"); files=sorted(p for p in root.rglob("*") if p.is_file()); print("".join(f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.relative_to(root).as_posix()}\\n" for p in files), end="")' \
  > "$RECOVERED_MANIFEST"
diff -u "$BACKUP_DIR/artifacts.sha256" "$RECOVERED_MANIFEST"
rm -- "$RECOVERED_MANIFEST"
```

`mongorestore --drop` is scoped to the fresh recovery project's database; never
run it against the original project or a database containing data to retain.
The restored Compose project uses the same `.env` values so token encryption
and database access remain compatible. The manifest comparison above verifies
every restored artifact's path and SHA-256. Verify representative documents,
versions, and PDFs through the UI/API before declaring recovery successful. If
a drill fails, stop the recovery project; the original named volumes remain
available.

After verification, stop the recovery project and resume the original project:

```bash
docker compose -p "$RECOVERY_PROJECT" --env-file .env down
docker compose up -d
```

`down` here removes only the isolated recovery containers/network; it leaves
its named volumes for inspection. Do not add `--volumes` to recovery or normal
project shutdown commands unless the exact data loss is intended and approved.

## Bootstrap and key handling after restore

Bootstrap is safe to rerun: it creates an administrator only if the restored
database contains no users and never resets an existing password or role. Do
not change bootstrap credentials to recover a restored account. Use the normal
password-reset/admin lifecycle, or create a new recovery environment only under
an explicitly approved procedure. Remove bootstrap credentials from `.env`
after first use.

Changing `APP_RATE_LIMIT_KEY` resets the effective rate-limit namespace;
changing `AI_PREVIEW_SIGNING_KEY` invalidates outstanding preview tokens.
Changing `INTEGRATION_ENCRYPTION_KEY` without a planned re-encryption process
breaks existing Google connections. Back up and restore configuration secrets
with the data, but never put their plaintext in the backup script, command
history, Git, or logs.
