#!/usr/bin/env bash
# Backup/restore drill: back up the running stack, restore into a brand-new isolated project
# (separate volumes, ports 18080/18443), verify the data arrived, then remove ONLY the drill project.
set -euo pipefail
cd "$(dirname "$0")/.."

DRILL=redshadow_drill
# The stack being backed up. Everything seeded and cleaned up below belongs to this project only.
SRC="${COMPOSE_PROJECT_NAME:-redshadow}"
TMP="$(mktemp -d)"

# Take the seeded rows and files out of the source stack again, also when a check fails part way.
cleanup() {
    rm -rf "$TMP"
    docker compose -p "$SRC" exec -T db psql -U redshadow_admin -d redshadow >/dev/null 2>&1 <<'SQL' || true
DROP TABLE IF EXISTS drill_marker;
DELETE FROM files_attachment WHERE id = '00000000-0000-4000-8000-0000000d0003';
DELETE FROM engagements_engagement WHERE id = '00000000-0000-4000-8000-0000000d0002';
DELETE FROM organisations_organisation WHERE id = '00000000-0000-4000-8000-0000000d0001';
SQL
    docker run --rm -v "${SRC}_media:/data" alpine:3.20 sh -c \
        'rm -f /data/drill.txt /data/2000/01/00000000-0000-4000-8000-0000000d0003; rmdir /data/2000/01 /data/2000 2>/dev/null' >/dev/null 2>&1 || true
}
trap cleanup EXIT

docker compose exec -T db psql -U redshadow_admin -d redshadow -c \
    "DROP TABLE IF EXISTS drill_marker; CREATE TABLE drill_marker(v text); INSERT INTO drill_marker VALUES ('drill-ok');" >/dev/null
docker run --rm -v ${SRC}_media:/data alpine:3.20 sh -c 'echo drill-media > /data/drill.txt && chown 10001:10001 /data/drill.txt'

# A real attachment: organisation, engagement, attachment row (plain SQL, so the live audit log is untouched)
# plus its blob in the media volume under a storage key, with the SHA-256 recorded in the row.
ORG=00000000-0000-4000-8000-0000000d0001; ENG=00000000-0000-4000-8000-0000000d0002
ATT=00000000-0000-4000-8000-0000000d0003; KEY="2000/01/$ATT"
docker run --rm -v ${SRC}_media:/data alpine:3.20 sh -c \
    "mkdir -p /data/2000/01 && printf 'drill attachment payload' > /data/$KEY && chmod 644 /data/$KEY && chown -R 10001:10001 /data/2000"
SHA="$(printf 'drill attachment payload' | shasum -a 256 | cut -d' ' -f1)"
docker compose exec -T db psql -U redshadow_admin -d redshadow -v ON_ERROR_STOP=1 >/dev/null <<SQL
DELETE FROM files_attachment WHERE id = '$ATT'; DELETE FROM engagements_engagement WHERE id = '$ENG';
DELETE FROM organisations_organisation WHERE id = '$ORG';
INSERT INTO organisations_organisation (id, created_at, updated_at, name, slug, industry, notes)
    VALUES ('$ORG', now(), now(), 'Drill Org', 'drill-org', '', '');
INSERT INTO engagements_engagement (id, created_at, updated_at, ref, organisation_id, name, type, status, status_before_archive,
    start_date, end_date, scope, out_of_scope, objectives, methodology, rules_of_engagement, version)
    VALUES ('$ENG', now(), now(), 'RS-E-2000-9999', '$ORG', 'Drill engagement', 'web', 'planned', '',
    '2000-01-01', '2000-01-02', '', '', '', '', '', 1);
INSERT INTO files_attachment (id, created_at, updated_at, kind, engagement_id, original_name, storage_key, mime, size, sha256, uploaded_by_id)
    VALUES ('$ATT', now(), now(), 'document', '$ENG', 'drill.txt', '$KEY', 'text/plain; charset=utf-8', 24, '$SHA',
    (SELECT id FROM accounts_user ORDER BY created_at LIMIT 1));
SQL

echo "==> backup"
scripts/backup.sh "$TMP"
BK="$(ls -d "$TMP"/*/ | head -1)"

echo "==> restore into fresh project $DRILL"
export COMPOSE_PROJECT_NAME="$DRILL" HTTP_PORT=18080 HTTPS_PORT=18443
docker compose -p "$DRILL" down -v >/dev/null 2>&1 || true
for v in secrets media; do docker volume rm "${DRILL}_${v}" >/dev/null 2>&1 || true; done
scripts/restore.sh "$BK" --yes

echo "==> verify"
GOT="$(docker compose -p "$DRILL" exec -T db psql -U redshadow_admin -d redshadow -tAc 'SELECT v FROM drill_marker')"
MEDIA="$(docker run --rm -v "${DRILL}_media:/data:ro" alpine:3.20 cat /data/drill.txt)"
ATT_ROW="$(docker compose -p "$DRILL" exec -T db psql -U redshadow_admin -d redshadow -tAc "SELECT sha256 FROM files_attachment WHERE id = '$ATT'")"
ATT_FILE="$(docker run --rm -v "${DRILL}_media:/data:ro" alpine:3.20 sha256sum "/data/$KEY" | cut -d' ' -f1)"
ASSET_TRIGGER="$(docker compose -p "$DRILL" exec -T db psql -U redshadow_admin -d redshadow -tAc "SELECT count(*) FROM pg_trigger WHERE tgname = 'engagement_asset_same_org'")"
[ "$ATT_ROW" = "$SHA" ] && [ "$ATT_FILE" = "$SHA" ] && [ "$ASSET_TRIGGER" = "1" ]
echo "restored attachment row, blob checksum and engagement-asset trigger verified"
TRIGGERS="$(docker compose -p "$DRILL" exec -T db psql -U redshadow_admin -d redshadow -tAc "SELECT count(*) FROM pg_trigger WHERE tgname LIKE 'audit_auditevent_no_%'")"
APP_UPDATE="$(docker compose -p "$DRILL" exec -T db psql -U redshadow_admin -d redshadow -tAc "SELECT has_table_privilege('redshadow_app','audit_auditevent','UPDATE')")"
[ "$TRIGGERS" = "2" ] && [ "$APP_UPDATE" = "f" ]
echo "audit append-only protections survived the restore"
NOTE_TRIGGER="$(docker compose -p "$DRILL" exec -T db psql -U redshadow_admin -d redshadow -tAc "SELECT count(*) FROM pg_trigger WHERE tgname = 'findings_note_no_update_delete'")"
REPORT_TEMPLATE="$(docker compose -p "$DRILL" exec -T db psql -U redshadow_admin -d redshadow -tAc "SELECT count(*) FROM reports_reporttemplate WHERE is_default")"
[ "$NOTE_TRIGGER" = "1" ] && [ "$REPORT_TEMPLATE" = "1" ]
echo "finding-note append-only trigger and the default report template survived the restore"
# Finding data in the restored copy: seed a finding and a note there (the drill project is thrown away), then prove
# the append-only trigger still refuses an UPDATE and a DELETE by the application role.
FORG=00000000-0000-4000-8000-0000000e0001; FENG=00000000-0000-4000-8000-0000000e0002
FFND=00000000-0000-4000-8000-0000000e0003; FNOTE=00000000-0000-4000-8000-0000000e0004
docker compose -p "$DRILL" exec -T db psql -U redshadow_admin -d redshadow -v ON_ERROR_STOP=1 >/dev/null <<SQL
INSERT INTO organisations_organisation (id, created_at, updated_at, name, slug, industry, notes)
    VALUES ('$FORG', now(), now(), 'Finding drill org', 'finding-drill-org', '', '');
INSERT INTO engagements_engagement (id, created_at, updated_at, ref, organisation_id, name, type, status, status_before_archive,
    start_date, end_date, scope, out_of_scope, objectives, methodology, rules_of_engagement, version)
    VALUES ('$FENG', now(), now(), 'RS-E-2000-9998', '$FORG', 'Finding drill', 'web', 'planned', '',
    '2000-01-01', '2000-01-02', '', '', '', '', '', 1);
INSERT INTO findings_finding (id, created_at, updated_at, ref, title, description, technical_details, poc, recommendation,
    "references", severity, cvss_version, cvss_vector, endpoint, status, discovered_at, dedupe_hash, source, version,
    engagement_id, reported_by_id, risk_acceptance_reason, import_issues)
    VALUES ('$FFND', now(), now(), 'RS-F-DRILL1', 'Drill finding', 'd', '', '', 'r', '[]', 'low', '', '', '', 'draft',
    '2000-01-01', 'drillhash', 'manual', 1, '$FENG', (SELECT id FROM accounts_user LIMIT 1), '', '[]');
INSERT INTO findings_findingnote (id, created_at, updated_at, kind, body, author_id, finding_id)
    VALUES ('$FNOTE', now(), now(), 'technical', 'original', (SELECT id FROM accounts_user LIMIT 1), '$FFND');
SQL
UPD="$(docker compose -p "$DRILL" exec -T db psql -U redshadow_admin -d redshadow -tA -c "SET ROLE redshadow_app; UPDATE findings_findingnote SET body = 'tampered' WHERE id = '$FNOTE'" 2>&1 || true)"
DEL="$(docker compose -p "$DRILL" exec -T db psql -U redshadow_admin -d redshadow -tA -c "SET ROLE redshadow_app; DELETE FROM findings_findingnote WHERE id = '$FNOTE'" 2>&1 || true)"
BODY="$(docker compose -p "$DRILL" exec -T db psql -U redshadow_admin -d redshadow -tAc "SELECT body FROM findings_findingnote WHERE id = '$FNOTE'")"
grep -q "append-only" <<<"$UPD" && grep -q "append-only" <<<"$DEL" && [ "$BODY" = "original" ]
echo "restored finding and note: the append-only trigger still refuses UPDATE and DELETE"
READY="$(curl -fsSk "https://localhost:18443/api/v1/health/ready")"
[ "$GOT" = "drill-ok" ] && [ "$MEDIA" = "drill-media" ] && grep -q '"status":"ok"' <<<"$READY"
echo "restored db row, media file and readiness verified"

echo "==> cleanup (drill project only)"
docker compose -p "$DRILL" down -v >/dev/null
echo "DRILL PASSED"
