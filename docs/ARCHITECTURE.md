# Architecture (summary)

Full design: [BLUEPRINT.md](BLUEPRINT.md). This file records what is implemented.

Modular monolith: one Django project, one PostgreSQL database, Celery and Redis for background work, Nginx as the
only entry point. Frontend is a Vite build served by Nginx. No microservices.

## Implemented in Phase 1

- Request path: Nginx (TLS, headers, size limit, request id) to gunicorn/Django to DRF.
- `apps/core`: abstract base models (UUID, timestamps, soft delete), request-id middleware, error envelope
  `{"error": {code, message, fields, request_id}}`, pagination (max 200), secret loader (`<NAME>_FILE`),
  log redaction, health endpoints, Celery `core.ping`.
- Default-deny API: the default permission needs a signed-in, unrestricted session; only health, CSRF and login views opt in with `AllowAny`.
- Database roles: `redshadow_owner` (DDL), `redshadow_app` (DML only). Public schema locked to those roles.
- Frontend: tokens, status shell with loading, success and error states, light and dark theme, responsive nav.

## Implemented in Phase 2

- `apps/accounts`: User (never hard-deleted), TOTP MFA, session authentication, restricted-session model, bootstrap command.
- `apps/rbac`: permission catalogue (`catalogue.py`, single source for seed, tests and docs/RBAC_PERMISSION_MATRIX.md), roles, resolver (`authz.py`), anti-escalation (`guards.py`), `ScopedModelViewSet`.
- `apps/audit`: hash-chained append-only log, `verify_audit`.
- Frontend: `src/design` (tokens, components, ui, Logo), `src/api`, `src/features/{auth,users,roles,account,home}`, `src/app`.

## Conventions for later phases

- Each Django app: `models.py`, `services.py` (all writes), `selectors.py` (scoped reads), `serializers.py`, `views.py`, `permissions.py`, `tests/`.
- Views never write models directly. Every list and detail read starts from the authz selectors (Phase 2).
- Tests run in the `backend-test` compose service against the real Postgres and Redis.

## Decision records

ADRs live in `docs/adr/`. Phase 1: 0001, 0002, 0005, 0007, 0008, 0011. Phase 2: 0003 RBAC model, 0004 audit chain, 0009 design adaptation, 0010 session and MFA.
