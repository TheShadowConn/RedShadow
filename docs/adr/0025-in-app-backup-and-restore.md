# ADR-0025: in-app backup and restore

Status: accepted (release 1.5.2, 2026-11-27)

## Decision

- A backup is a tar of one `COPY` dump per table (one repeatable-read snapshot), the media files, the key that seals two-step secrets and a manifest, encrypted with a passphrase (scrypt, AES-256-GCM in numbered chunks). `pg_dump` is not needed.
- Restore is allowed only while there is no organisation, engagement or finding, and only when the applied migrations are identical. It loads the rows in one transaction with `session_replication_role = replica` and re-seals two-step secrets with the new installation's key.
- Restore needs the database administrator, so a separate `maintenance` service does it. The web application checks the file and passphrase, unpacks into the `staging` volume and queues the request.
- Both actions are for Super Admins and ask for the password (and two-step code) again.

## Limits

- The unpacked data lies unencrypted in the `staging` volume until the restore ends.
- All application containers mount the `secrets` volume, which includes the database administrator password (this predates the feature). Splitting that volume would close it.
- An older backup cannot be restored into a newer layout directly: install the old version, restore, upgrade.
