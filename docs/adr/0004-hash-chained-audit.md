# ADR-0004 Custom hash-chained audit log

Status: accepted (2026-11-12)

**Decision:** audit.AuditEvent is append-only and hash-chained (SHA-256 over canonical JSON plus the previous hash) under a Postgres advisory lock, written in the caller's transaction. The database blocks UPDATE, DELETE and TRUNCATE with triggers and revoked privileges for the runtime role.

**Why:** Third-party audit packages cannot give a verifiable chain, transaction-bound writes and redaction together. A chain proves tampering only if the head hash is also kept elsewhere.

**Consequences:** Appends are serialised (fine at team scale). manage.py verify_audit checks the chain. scripts/restore.sh re-applies the privilege revokes (db/sql/post-restore.sql). Export of the chain head off-host is recommended; scheduled verification arrives in Phase 6.
