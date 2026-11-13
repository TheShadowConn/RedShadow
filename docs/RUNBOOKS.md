# Runbooks

Commands run from the project folder on the host. Never use `docker compose down -v` or delete volumes on the real project: that removes the database, files and secrets. Use a throwaway project name (`-p rs_test`) for experiments.

## Start, stop, status

```bash
make up        # build and start (data is kept)
make ps        # service health
make logs      # follow logs
make down      # stop (data is kept)
```

Services: `db`, `redis`, `migrate` (runs once), `backend`, `worker` (default, imports, maintenance), `reports-worker` (PDF), `beat`, `nginx`.

## Upgrade to a new version

1. `scripts/backup.sh` and copy the backup off this machine.
2. Replace the source folder contents (keep `.env` and `tls/`).
3. `make up`. The `migrate` service applies migrations before the backend starts. Volumes are untouched.
4. `make smoke` (34 checks, including that data survives a restart and a rebuild).
5. Roll back: stop, restore the source folder of the previous version, `scripts/restore.sh backups/<timestamp> --yes` (migrations are forward only).

## Backup and restore

See `BACKUP_RESTORE.md`. `make drill` proves it on a throwaway project: database, media, secrets, append-only protections and the default report template.

## Secrets

All secrets live in the `secrets` volume (`secret_key`, `mfa_key`, database and Redis passwords, TLS key). Losing `mfa_key` makes every enrolled MFA secret unreadable (admin reset needed); losing `secret_key` signs everyone out. They are inside `secrets.tgz` of each backup.

Rotate a database password: change it in Postgres (`ALTER ROLE`), write the same value to the file in the `secrets` volume, `docker compose restart backend worker reports-worker beat`.

## Admin locked out

- Forgot password or lost authenticator: another Super Admin resets it (Users page). Every reset is audited and revokes sessions.
- No Super Admin can sign in: `docker compose run --rm migrate python manage.py bootstrap_admin` only creates an admin when none exists. If one exists, reset through the database as `redshadow_admin` (set the Argon2 hash with `manage.py shell` and `must_change_password=True`), then record the reason in the incident notes.

## Audit chain reports "broken"

1. Audit page, Verify now. Note the first bad event number.
2. Do not edit or delete anything. Take a backup (`scripts/backup.sh`).
3. Compare with a backup taken before the first bad event: restore it into a throwaway project (`scripts/restore.sh`) and verify that copy. If the older copy verifies and the live one does not, records were changed after the backup; restoring from the good backup is the repair.
4. Check who holds database admin access and the application log around that time.

## Reports

- A report stays "Building" for more than a few minutes: `docker compose logs reports-worker --tail 100`; the daily cleanup also fails jobs stuck for 15 minutes. Create it again.
- Out of memory kills (`docker inspect` shows OOMKilled): lower the finding count with filters, or raise `mem_limit` of `reports-worker` in `docker-compose.yml`.
- A file answers 410: it expired (`REPORT_RETENTION_DAYS`, default 90). Create a new one.
- Template logo wrong: Report styles, replace the logo (PNG or JPEG, 1 MB, 2000 px).

## Imports

A stuck import is closed by the daily cleanup after 30 minutes. A failed all-or-nothing import leaves zero findings. Uploaded files are deleted after 30 days.

## Disk and cleanup

`docker system df`. Prune only dangling build cache (`docker builder prune`). Never prune volumes.

## LAN access

Set `TLS_EXTRA_SAN`, `ALLOWED_HOSTS` (and `CSRF_TRUSTED_ORIGINS` for non-default ports) in `.env`, remove the `tls` folder in the secrets volume (or use `TLS_MODE=provided` with your own certificate), then `make up`.

## Throwaway test project (safe to delete)

```bash
COMPOSE_PROJECT_NAME=rs_test HTTP_PORT=18081 HTTPS_PORT=18444 TLS_MODE=off docker compose -p rs_test up --build -d --wait
docker compose -p rs_test down -v      # removes ONLY this project's volumes
```
