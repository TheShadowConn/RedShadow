# ADR-0001 Modular monolith

Status: accepted (2026-11-12)

**Decision:** One Django project, one PostgreSQL database, strict app boundaries; Celery only for async work.

**Why:** Authorisation is the core risk: one process and one resolver is the safest place to get it right. Transactions span modules (finding change plus audit event).

**Consequences:** No network trust boundaries between modules. Scaling is vertical; acceptable for team-sized use.
