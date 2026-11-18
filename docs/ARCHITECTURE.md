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

- `apps/accounts`: User (deleted accounts are removed or anonymised, see ADR-0021), TOTP MFA, session authentication, restricted-session model, bootstrap command.
- `apps/rbac`: permission catalogue (`catalogue.py`, single source for seed, tests and docs/RBAC_PERMISSION_MATRIX.md), roles, resolver (`authz.py`), anti-escalation (`guards.py`), `ScopedModelViewSet`.
- `apps/audit`: hash-chained append-only log, `verify_audit`.
- Frontend: `src/design` (tokens, components, ui, Logo), `src/api`, `src/features/{auth,users,roles,account,home}`, `src/app`.

## Assets, imports and user deletion (2026-11-18)

- `apps/organisations/identifiers.py` (pure functions: kinds, normalisation, kind detection, cell splitting) and `assets.py` (identifier, onboarding, delete and merge logic under the organisation row lock). `AssetIdentifier` enforces one owner per identifier per organisation (ADR-0018).
- `apps/imports`: `ImportJob.kind` is `findings` or `assets`. `asset_import.py` holds the asset row validator and the `Matcher` shared by the check and the commit (ADR-0019). `services.py` gained corrected-file re-upload, retry, delete and attempt history (ADR-0020); every read of a job's rows goes through `ImportJob.rows_now`.
- `apps/accounts/user_services.py`: `deletion_impact` and `delete_user`, removing or anonymising the account (ADR-0021).
- Frontend: `features/assets/` (Assets page, shared `AssetEditor` with live identifier check, used by the organisation page too); `features/imports/` handles both kinds; `features/users/` has the delete dialog.
- Schema: [SCHEMA.md](SCHEMA.md). API: [API.md](API.md). User guide: [ASSETS_AND_IMPORTS.md](ASSETS_AND_IMPORTS.md).

## Conventions for later phases

- Each Django app: `models.py`, `services.py` (all writes), `selectors.py` (scoped reads), `serializers.py`, `views.py`, `permissions.py`, `tests/`.
- Views never write models directly. Every list and detail read starts from the authz selectors (Phase 2).
- Tests run in the `backend-test` compose service against the real Postgres and Redis.

## Decision records

ADRs live in `docs/adr/`. Phase 1: 0001, 0002, 0005, 0007, 0008, 0011. Phase 2: 0003 RBAC model, 0004 audit chain, 0009 design adaptation, 0010 session and MFA. Later: 0012 to 0017 (engagements, findings, audit, calendar, import, dashboards), 0018 asset identifiers, 0019 onboarding and asset import, 0020 import attempts, 0021 user deletion.
