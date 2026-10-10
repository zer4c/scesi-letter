#!/usr/bin/env bash
set -euo pipefail

if [[ "$#" -ne 1 || "$1" != /* ]]; then
  printf 'Usage: %s /absolute/path/to/restricted-backup-directory\n' "$0" >&2
  exit 2
fi

backup_root="$1"
umask 077
compose_args=()
if [[ -n "${SCESI_ENV_FILE:-}" ]]; then
  compose_args=(--env-file "$SCESI_ENV_FILE")
fi
compose() {
  docker compose "${compose_args[@]}" "$@"
}

running_services="$(compose ps --status running --services)"
for service in backend worker; do
  case " $running_services " in
    *" $service "*)
      printf 'Stop the %s service before backing up MongoDB and artifacts.\n' "$service" >&2
      exit 1
      ;;
  esac
done

mkdir -p -- "$backup_root"
backup_path="$backup_root/scesi-$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -m 700 -- "$backup_path"

database_name="$(compose run --rm --no-deps -T backend python -c 'from app.core.config import Settings; print(Settings().MONGODB_DATABASE)')"
if [[ ! "$database_name" =~ ^[A-Za-z0-9_-]+$ ]]; then
  printf 'Configured MongoDB database name is not safe for a backup command.\n' >&2
  exit 1
fi

compose exec -T mongodb bash -ec \
  'mongodump --username "$MONGO_INITDB_ROOT_USERNAME" --password "$MONGO_INITDB_ROOT_PASSWORD" --authenticationDatabase admin --db "$1" --archive --gzip' \
  _ "$database_name" > "$backup_path/mongodb.archive.gz"

compose run --rm --no-deps -T backend \
  python -c 'import hashlib; from pathlib import Path; root=Path("/var/lib/scesi/artifacts"); files=sorted(p for p in root.rglob("*") if p.is_file()); print("".join(f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.relative_to(root).as_posix()}\n" for p in files), end="")' \
  > "$backup_path/artifacts.sha256"
compose run --rm --no-deps -T backend \
  tar -C /var/lib/scesi -czf - artifacts \
  > "$backup_path/artifacts.tar.gz"

(cd "$backup_path" && sha256sum mongodb.archive.gz artifacts.tar.gz > SHA256SUMS)
chmod 600 "$backup_path"/*
printf 'Backup created: %s\n' "$backup_path"
printf 'Protect this directory as sensitive data; it contains letters and recipient information.\n'
