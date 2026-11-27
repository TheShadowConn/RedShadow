#!/usr/bin/env bash
# Restore a backup made by scripts/backup.sh. DESTRUCTIVE: replaces the database and media.
# Usage: scripts/restore.sh <backup-dir> --yes
#  - Fresh install (no secrets volume yet): secrets are restored first so keys match the data.
#  - Existing install: existing secrets are kept (the database roles already use them).
set -euo pipefail
cd "$(dirname "$0")/.."

DIR="${1:-}"
[ -d "$DIR" ] || { echo "usage: $0 <backup-dir> --yes" >&2; exit 2; }
[ "${2:-}" = "--yes" ] || { echo "Restore replaces the database and media. Re-run with --yes." >&2; exit 2; }
DIR="$(cd "$DIR" && pwd)"
PROJECT="${COMPOSE_PROJECT_NAME:-redshadow}"

echo "==> verifying checksums"
(cd "$DIR" && shasum -a 256 -c SHA256SUMS)

if ! docker volume inspect "${PROJECT}_secrets" >/dev/null 2>&1; then
    echo "==> fresh install: restoring secrets"
    docker volume create \
        --label "com.docker.compose.project=${PROJECT}" \
        --label "com.docker.compose.volume=secrets" "${PROJECT}_secrets" >/dev/null
    docker run --rm -v "${PROJECT}_secrets:/data" -v "$DIR:/in:ro" alpine:3.20 \
        tar -C /data -xzf /in/secrets.tgz
else
    echo "==> existing secrets kept"
fi

echo "==> stopping application services"
docker compose stop nginx backend worker reports-worker maintenance beat >/dev/null 2>&1 || true
docker compose up -d --wait db

echo "==> recreating database"
docker compose exec -T db psql -v ON_ERROR_STOP=1 -U redshadow_admin -d postgres <<'SQL'
DROP DATABASE IF EXISTS redshadow WITH (FORCE);
CREATE DATABASE redshadow OWNER redshadow_owner;
REVOKE ALL ON DATABASE redshadow FROM PUBLIC;
GRANT CONNECT ON DATABASE redshadow TO redshadow_app;
SQL
docker compose exec -T db psql -v ON_ERROR_STOP=1 -U redshadow_admin -d redshadow \
    -f /opt/redshadow/sql/harden.sql >/dev/null

echo "==> restoring dump"
docker compose exec -T db pg_restore -U redshadow_admin -d redshadow \
    --no-owner --role=redshadow_owner --exit-on-error < "$DIR/db.dump"

echo "==> re-applying audit privilege restrictions"
docker compose exec -T db psql -v ON_ERROR_STOP=1 -U redshadow_admin -d redshadow \
    -f /opt/redshadow/sql/post-restore.sql >/dev/null

echo "==> restoring media"
docker volume inspect "${PROJECT}_media" >/dev/null 2>&1 || docker volume create \
    --label "com.docker.compose.project=${PROJECT}" \
    --label "com.docker.compose.volume=media" "${PROJECT}_media" >/dev/null
docker run --rm -v "${PROJECT}_media:/data" -v "$DIR:/in:ro" alpine:3.20 \
    sh -c 'find /data -mindepth 1 -delete && tar -C /data -xzf /in/media.tgz && chown -R 10001:10001 /data'

echo "==> starting stack (migrations run first)"
docker compose up -d --build --wait
echo "==> verifying audit chain"
docker compose exec -T backend python manage.py verify_audit
echo "restore complete"
