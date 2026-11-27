# Backup and restore

## In the app (1.5.2)

A Super Admin opens **Backup and restore**. **Create and download** gives one passphrase-encrypted `.rsbk` file with all data, uploads and the two-step sign-in key. Restore it on a new, empty installation of the same version; it is refused once an organisation or engagement exists. See ADR-0025 and the user manual. The in-app restore accepts up to 2 GB and is carried out by the `maintenance` service.

The command-line tools below remain: they also keep the TLS certificate and database passwords, and have no size limit.

## Backup

After a successful run the script records the backup in the app (`manage.py record_backup`, one audit event named `system.backup_completed`). Super Admins see the newest one on the About page, with a warning when it is older than `BACKUP_WARN_DAYS` (default 7). If recording fails, the backup itself is still fine and the script prints a note.

```bash
scripts/backup.sh            # writes ./backups/<timestamp>/
```

Produces `db.dump` (pg_dump custom format), `media.tgz`, `secrets.tgz`, `SHA256SUMS`. Directory mode 0700.
The stack keeps running. `secrets.tgz` contains the Django secret key, MFA encryption key, database passwords and TLS key: store the
backup somewhere access-controlled. Copy backups off this Mac regularly.

## Restore

```bash
scripts/restore.sh backups/<timestamp> --yes
```

Destructive: replaces the database and media. Steps: verify checksums; if no `secrets` volume exists (fresh install)
restore secrets first, otherwise keep existing ones; stop app services; recreate the `redshadow` database with the
standard role grants; `pg_restore`; re-apply audit privilege restrictions (`db/sql/post-restore.sql`); restore media; start the stack (migrations run before the backend); verify the audit chain.

To restore on a new machine: clone/copy the project, run `scripts/restore.sh <backup> --yes` (do not start the stack first).

## Drill

```bash
scripts/backup-drill.sh
```

Backs up the live stack, restores into an isolated project `redshadow_drill` (ports 18080/18443, separate volumes),
verifies a database row, a media file and readiness, then removes only the drill project. Last run: passed (2026-11-12).

## Later phases

The drill also checks that the audit append-only protections survived. Phase 12 repeats the drill with real data and an upgrade.
