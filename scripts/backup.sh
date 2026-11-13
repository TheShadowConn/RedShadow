#!/usr/bin/env bash
# Backup: PostgreSQL dump + media volume + secrets volume, with a SHA-256 manifest.
# Usage: scripts/backup.sh [output-root]   (default ./backups)
# The secrets archive holds SECRET_KEY, DB passwords and TLS key: store backups securely.
set -euo pipefail
cd "$(dirname "$0")/.."

PROJECT="${COMPOSE_PROJECT_NAME:-redshadow}"
ROOT="${1:-${BACKUP_DIR:-./backups}}"
OUT="$ROOT/$(date +%Y%m%d-%H%M%S)"
umask 077
mkdir -p "$OUT"
OUT_ABS="$(cd "$OUT" && pwd)"

echo "==> database dump"
docker compose exec -T db pg_dump -U redshadow_admin -Fc redshadow > "$OUT/db.dump"

for vol in media secrets; do
    echo "==> $vol volume"
    docker run --rm -v "${PROJECT}_${vol}:/data:ro" -v "$OUT_ABS:/out" alpine:3.20 \
        tar -C /data -czf "/out/${vol}.tgz" .
done

(cd "$OUT" && shasum -a 256 db.dump media.tgz secrets.tgz > SHA256SUMS)
echo "backup complete: $OUT"
