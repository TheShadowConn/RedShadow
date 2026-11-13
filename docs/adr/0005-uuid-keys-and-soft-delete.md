# ADR-0005 UUID keys and soft delete

Status: accepted (2026-11-12)

**Decision:** UUID v4 primary keys on business tables; soft delete via deleted_at; human refs for display only.

**Why:** Non-enumerable ids reduce IDOR guessing. Soft delete preserves history and audit links.

**Consequences:** Default manager hides deleted rows; use all_objects explicitly. Base classes in apps/core/models.py.
