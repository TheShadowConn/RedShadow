# Administration and security

{SA} This chapter is for the people who run the RedShadow installation. It summarises the operating tasks. The detailed procedures are in the project documents `README.md`, `docs/DOCKER_SETUP.md`, `docs/BACKUP_RESTORE.md`, `docs/RUNBOOKS.md` and `docs/SECURITY.md`.

## Start, stop and upgrade

| Task | Command |
|---|---|
| Start everything (build if needed) | `docker compose up --build -d --wait` or `make up` |
| Stop, keeping all data | `docker compose down` |
| Check service health | `docker compose ps` |
| Run the smoke test (34 checks) | `make smoke` |
| Verify the audit chain | `docker compose exec backend python manage.py verify_audit` |

> **Warning:** Never run `docker compose down -v` on a real installation. It deletes the database, the uploaded files and the secrets.

Upgrades keep your data: pull the new version, run `make backup`, then `make up`. Database migrations run automatically and the application never deletes data during a normal rebuild.

## First sign-in

The first Super Admin is created once, at the first start, with the email `admin@redshadow.local` unless you set `BOOTSTRAP_ADMIN_EMAIL`. The generated password is printed once in the migration log:

```
docker compose logs migrate | grep -A3 "FIRST LOGIN"
```

At the first sign-in you must change the password and enrol two-step verification. Create named accounts for everyone and keep the bootstrap account for emergencies.

## Backup and restore

- `make backup` writes a dated folder under `backups/` with the database and the uploaded files.
- `make restore DIR=backups/<stamp>` restores it. **This replaces the current data at once and does not ask again**, so check the folder name first.
- `make drill` rehearses a full restore in an isolated copy and checks the data, the files and the audit protections. Run it after upgrades and before relying on a backup.

Keep backups on another machine and protect them like the database: they contain client findings.

## Settings you may change

Settings are environment variables in `.env` (see `.env.example`). The most useful:

| Setting | Meaning | Default |
|---|---|---|
| `HTTP_PORT`, `HTTPS_PORT` | Published ports | 80, 443 |
| `TLS_MODE` | `selfsigned`, `provided` or `off` | `selfsigned` |
| `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS` | Names and origins people use to reach RedShadow | localhost |
| `SESSION_IDLE_SECONDS`, `SESSION_ABSOLUTE_SECONDS` | Session limits | 1800, 43200 |
| `UPLOAD_MAX_MB` | Evidence and document size limit | 25 |
| `SLA_DAYS_CRITICAL`, `_HIGH`, `_MEDIUM`, `_LOW` | Fix targets in days | 7, 30, 90, 180 |
| `RISK_ACCEPT_MAX_DAYS` | Longest risk acceptance | 365 |
| `REPORT_RETENTION_DAYS` | How long report files are kept | 90 |
| `APP_VERSION` | Version shown on the About page | 1.1.0 |

After changing a value run `make up` to apply it.

## Security features at a glance

| Area | Protection |
|---|---|
| Sign-in | Argon2 password hashing, 12 character minimum, lockout after 5 failures, rate limits, optional or required two-step verification (TOTP) with recovery codes. |
| Sessions | HttpOnly cookies stored server side, idle and absolute timeouts, instant revocation, CSRF protection on every change. |
| Access | Roles plus engagement scope, checked on the server for every request. Out-of-scope records answer as not found. |
| Privilege | No self-promotion, no granting more than you hold, last Super Admin protected, role changes sign people out. |
| Files | Type checked by content, allow-list, size limit, images re-encoded, no HTML or SVG, downloads sent as attachments through a protected path. |
| Audit | Append-only, hash-chained, enforced by the database, verified nightly and on demand. |
| Platform | Only the web proxy is published, containers run without extra privileges, secrets are generated into a private volume, the internal network has no outbound access. |

## Handling common admin requests

| Request | Do this |
|---|---|
| A person lost their phone | **Users**, open the person, **Reset two-step verification**. |
| A person forgot their password | **Reset password**, give the one-time password securely. |
| Someone left the company | **Deactivate** the account. History stays attributed. |
| A vendor finished their work | Remove them from the engagement **Team** tab or deactivate them. |
| A client asks who changed a finding | Open the finding, **History**, or filter the **Audit** page by record. |
| Need a limited internal role | Create a custom role under **Roles**. |
