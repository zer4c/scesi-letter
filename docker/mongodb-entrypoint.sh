#!/usr/bin/env bash
set -euo pipefail

keyfile=/data/configdb/replica-set.key
if [[ ! -s "$keyfile" ]]; then
  openssl rand -base64 756 > "$keyfile"
fi

chown mongodb:mongodb "$keyfile"
chmod 0400 "$keyfile"

exec /usr/local/bin/docker-entrypoint.sh "$@" --keyFile "$keyfile"
