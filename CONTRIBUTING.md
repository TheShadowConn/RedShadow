# Contributing to RedShadow

Thanks for helping. This is a modular monolith: Django REST backend, React and TypeScript frontend, PostgreSQL, Celery and Redis, all run by Docker Compose.

## Ground rules

- Read [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md), [docs/BLUEPRINT.md](docs/BLUEPRINT.md) and the ADRs in `docs/adr/` first.
- Open an issue before large changes so the design can be agreed.
- Keep changes small and focused. No unrelated refactoring.
- Security first: enforce permissions on the server, validate every input, never log secrets, and keep audit writes in the same transaction as the change.
- By contributing you agree your work is licensed under Apache-2.0. Do not add code you cannot license that way.
- Do not add logos, names or brand assets of your own to the project's brand files (see `TRADEMARKS.md`).

## Backend conventions

Each app uses `models.py`, `services.py` (all writes), `selectors.py` (scoped reads), `serializers.py`, `views.py`, `urls.py`. Views never write models directly. Every read starts from a scoped queryset. New viewsets derive from `ScopedModelViewSet` with a default-deny `permission_map`. Every new route is added to `COVERED_ROUTES` in `backend/tests/test_rbac.py`.

## Run and test

```bash
docker compose up --build -d --wait                        # start
make test                                                  # backend tests (real Postgres and Redis)
make lint                                                  # ruff
cd frontend && npm ci && npx tsc --noEmit && npm run build # frontend checks
make smoke                                                 # 34 stack checks
make manual                                                # rebuild the PDF manual
```

Never run `docker compose down -v` against data you care about.

## Pull requests

1. Fork, branch, commit with clear messages.
2. Add or update tests. Do not weaken or delete tests to make them pass.
3. Run lint, tests and the frontend checks.
4. Update docs, and `docs/RBAC_PERMISSION_MATRIX.md` if you change permissions (`manage.py rbac_matrix`).
5. Describe what changed and how you tested it.
