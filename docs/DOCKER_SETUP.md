# Docker setup

## Services

| Service | Image | Published | Notes |
|---|---|---|---|
| secrets-init | alpine + openssl (built) | no | One-shot. Generates missing secrets and self-signed cert into volume `secrets`. Never overwrites. |
| db | postgres:16-alpine | no | Roles: `redshadow_admin` (bootstrap superuser, ops only), `redshadow_owner` (migrations), `redshadow_app` (DML only). |
| redis | redis:7-alpine | no | Password required, no persistence. |
| migrate | backend image | no | One-shot: `migrate` as `redshadow_owner`, then `bootstrap_admin` (creates the first Super Admin once; password printed once in these logs). |
| backend | backend image | no | gunicorn, runs as `redshadow_app`, uid 10001, read-only root fs. |
| worker | backend image | no | Celery queues: default, imports, reports, maintenance. |
| beat | backend image | no | Celery beat, schedule file on volume `beat`. |
| nginx | built (frontend + nginx-unprivileged) | 80, 443 | Only published service. TLS, security headers, `/api` proxy, SPA. |

Start order: secrets-init, then db and redis healthy, then migrate, then backend and worker, then beat and nginx.

## Networks and volumes

- `edge`: nginx. `internal` (no outbound route): everything else.
- Volumes `pgdata`, `media`, `beat`, `secrets`. Normal `up`, `down`, `restart` and rebuilds keep them.

## Configuration

`.env` (copy of `.env.example`) holds non-secret settings only. Variables: `HTTP_PORT`, `HTTPS_PORT`,
`TLS_MODE` (`off|selfsigned|provided`), `TLS_HOSTNAME`, `TLS_EXTRA_SAN`, `TLS_CERT_DIR`, `ALLOWED_HOSTS`, `LOG_LEVEL`.

- `selfsigned`: certificate for `localhost`, `127.0.0.1` and `TLS_HOSTNAME`. To cover a LAN IP or name set `TLS_EXTRA_SAN`
  (for example `IP:192.168.1.20`) and `ALLOWED_HOSTS`, then delete the `tls` folder in the secrets volume and restart.
- `provided`: place `tls.crt` and `tls.key` in `TLS_CERT_DIR` (default `./tls`).
- HSTS is sent only when TLS is on.

## Secrets

Files in volume `secrets` (mounted read-only at `/run/secrets`): `secret_key`, `db_admin_password`,
`db_owner_password`, `db_app_password`, `redis_password`, `mfa_key` (encrypts MFA secrets: never lose it), `tls/`. Optional `bootstrap_admin_password`: if present it is used for the first admin instead of a generated one. Mode 0444 on an internal-only volume.
Back them up with `scripts/backup.sh` (included). Losing `secret_key` invalidates sessions; losing `mfa_key` makes every enrolled MFA secret unreadable.
Keep the secrets archive together with the database dump.

## Commands

- Start: `docker compose up --build -d --wait`. Stop: `docker compose down`.
- Tests: `docker compose --profile test run --rm backend-test`.
- `docker compose down -v` destroys all data. Do not use on a real install.

## Upgrades

Rebuild and start; `migrate` runs before backend. Migrations must stay backward-compatible within one release.
