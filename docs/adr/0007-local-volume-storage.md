# ADR-0007 Local volume storage behind an interface

Status: accepted (2026-11-12)

**Decision:** Uploads live on the media volume with random storage keys, served only through an authorised endpoint (Nginx X-Accel).

**Why:** Simple, no extra service. An interface leaves room for S3 or MinIO later.

**Consequences:** No object-store features now. Volume must be backed up with the database. Implemented from Phase 3.
