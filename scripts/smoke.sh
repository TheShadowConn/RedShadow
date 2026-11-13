#!/usr/bin/env bash
# Smoke test: start, health, headers, isolation, DB privileges, persistence across restart + rebuild.
set -euo pipefail
cd "$(dirname "$0")/.."

PASS=0
check() { # check "<name>" <command...>
    local name="$1"; shift
    if "$@" >/dev/null 2>&1; then echo "PASS  $name"; PASS=$((PASS+1)); else echo "FAIL  $name"; exit 1; fi
}
absent() { ! "$@"; }

HTTPS_PORT="${HTTPS_PORT:-443}"
HTTP_PORT="${HTTP_PORT:-80}"
BASE="https://localhost:${HTTPS_PORT}"
[ "${TLS_MODE:-selfsigned}" = "off" ] && BASE="http://localhost:${HTTP_PORT}"
psql_admin() { docker compose exec -T db psql -v ON_ERROR_STOP=1 -U redshadow_admin -d redshadow -tA "$@"; }

echo "== start"
docker compose up --build -d --wait
check "all long-running services healthy" test -z "$(docker compose ps --format '{{.Health}}' --status running | grep -v healthy || true)"

echo "== http"
check "live endpoint"  bash -c "curl -fsSk $BASE/api/v1/health/live | grep -q '\"ok\"'"
check "ready checks db+redis" bash -c "curl -fsSk $BASE/api/v1/health/ready | grep -q '\"database\":\"ok\".*\"redis\":\"ok\"'"
check "SPA served at /" bash -c "curl -fsSk $BASE/ | grep -q 'id=\"root\"'"
check "SPA fallback route" bash -c "curl -fsSk $BASE/some/deep/route | grep -q 'id=\"root\"'"
check "unknown api -> JSON error envelope" bash -c "curl -sk $BASE/api/v1/nope | grep -q '\"not_found\"'"
HEAD="$(curl -sk -D - -o /dev/null "$BASE/")"
check "CSP header"          grep -qi '^content-security-policy:.*frame-ancestors' <<<"$HEAD"
check "nosniff header"      grep -qi '^x-content-type-options: nosniff' <<<"$HEAD"
check "no server version"   absent grep -Eqi '^server: nginx/' <<<"$HEAD"
check "request id returned" bash -c "curl -sk -D - -o /dev/null $BASE/api/v1/health/live | grep -qi '^x-request-id: '"
if [ "$BASE" != "http://localhost:${HTTP_PORT}" ]; then
    check "http redirects to https" bash -c "curl -sI http://localhost:${HTTP_PORT}/ | grep -q '301'"
    check "HSTS on TLS" bash -c "curl -skI $BASE/ | grep -qi '^strict-transport-security'"
fi

echo "== isolation"
check "only nginx publishes ports" test "$(docker compose ps --format '{{.Service}} {{.Ports}}' | grep -E '0\.0\.0\.0:' | awk '{print $1}' | sort -u | tr '\n' ' ')" = "nginx "
check "postgres not on host" absent nc -z -w2 localhost 5432
check "redis not on host"    absent nc -z -w2 localhost 6379
check "backend runs non-root" test "$(docker compose exec -T backend id -u)" = "10001"
APP_PW="$(docker compose exec -T db cat /run/secrets/db_app_password)"
check "app role cannot create tables (permission denied)" bash -c "docker compose exec -T -e PGPASSWORD='$APP_PW' db psql -h 127.0.0.1 -U redshadow_app -d redshadow -c 'CREATE TABLE smoke_ddl(a int)' 2>&1 | grep -q 'permission denied'"
check "app role can read" docker compose exec -T -e PGPASSWORD="$(docker compose exec -T db cat /run/secrets/db_app_password)" db \
    psql -h 127.0.0.1 -U redshadow_app -d redshadow -tAc "SELECT 1"
check "redis requires password" bash -c "docker compose exec -T redis redis-cli ping 2>&1 | grep -q NOAUTH"

echo "== auth and audit"
check "protected API rejects anonymous (401)" bash -c "test \"\$(curl -sk -o /dev/null -w '%{http_code}' $BASE/api/v1/users)\" = 401"
check "login without CSRF token is refused (403)" bash -c "test \"\$(curl -sk -o /dev/null -w '%{http_code}' -X POST -H 'Content-Type: application/json' -d '{\"email\":\"a@b.c\",\"password\":\"x\"}' $BASE/api/v1/auth/login)\" = 403"
check "CSRF endpoint answers" bash -c "curl -sk $BASE/api/v1/auth/csrf | grep -q csrfToken"
check "bootstrap Super Admin exists" test "$(psql_admin -c "SELECT count(*) FROM accounts_user u JOIN rbac_role r ON r.id = u.role_id WHERE r.system_key = 'super_admin'")" -ge 1
check "system roles and catalogue seeded" test "$(psql_admin -c "SELECT count(*) FROM rbac_role WHERE system_key IS NOT NULL")" = 4
check "audit chain verifies" docker compose exec -T backend python manage.py verify_audit
check "app role cannot UPDATE audit rows (permission denied)" bash -c "docker compose exec -T -e PGPASSWORD='$APP_PW' db psql -h 127.0.0.1 -U redshadow_app -d redshadow -c \"UPDATE audit_auditevent SET action='x'\" 2>&1 | grep -q 'permission denied'"
check "app role cannot DELETE audit rows (permission denied)" bash -c "docker compose exec -T -e PGPASSWORD='$APP_PW' db psql -h 127.0.0.1 -U redshadow_app -d redshadow -c 'DELETE FROM audit_auditevent' 2>&1 | grep -q 'permission denied'"
OWNER_PW="$(docker compose exec -T db cat /run/secrets/db_owner_password)"
check "even the table owner is blocked by the append-only trigger" bash -c "docker compose exec -T -e PGPASSWORD='$OWNER_PW' db psql -h 127.0.0.1 -U redshadow_owner -d redshadow -c \"UPDATE audit_auditevent SET action='x'\" 2>&1 | grep -q 'append-only'"

echo "== celery"
check "worker answers ping" docker compose exec -T worker celery -A config inspect ping -t 5
docker compose exec -T worker celery -A config call core.ping >/dev/null
sleep 3
check "ping task executed" bash -c "docker compose logs worker 2>&1 | grep -q 'core.ping.*succeeded'"

echo "== persistence"
psql_admin -c "DROP TABLE IF EXISTS smoke_persist; CREATE TABLE smoke_persist(v text); INSERT INTO smoke_persist VALUES ('survives');" >/dev/null
check "row present" test "$(psql_admin -c 'SELECT v FROM smoke_persist')" = "survives"
docker compose restart >/dev/null 2>&1; docker compose up -d --wait >/dev/null 2>&1
check "row survives restart" test "$(psql_admin -c 'SELECT v FROM smoke_persist')" = "survives"
docker compose up --build -d --wait >/dev/null 2>&1
check "row survives rebuild" test "$(psql_admin -c 'SELECT v FROM smoke_persist')" = "survives"
check "services still healthy after rebuild" bash -c "curl -fsSk $BASE/api/v1/health/ready | grep -q '\"status\":\"ok\"'"
psql_admin -c "DROP TABLE smoke_persist" >/dev/null

echo "ALL $PASS CHECKS PASSED"
