.PHONY: up down build logs ps test lint smoke backup restore drill manual schema

up:
	BUILD_ID="$$(date -u +%Y%m%d.%H%M)" BUILD_DATE="$$(date -u +%Y-%m-%d)" docker compose up --build -d --wait

# Stops containers. Never removes volumes (data is kept).
down:
	docker compose down

build:
	docker compose build

logs:
	docker compose logs -f --tail=100

ps:
	docker compose ps

test:
	docker compose --profile test run --rm backend-test

lint:
	docker compose --profile test run --rm backend-test ruff check --no-cache .

smoke:
	scripts/smoke.sh

backup:
	scripts/backup.sh

# make restore DIR=backups/20260101-120000
restore:
	scripts/restore.sh $(DIR) --yes

drill:
	scripts/backup-drill.sh

# Builds docs/manual/RedShadow-User-Manual.pdf with WeasyPrint inside the backend test image.
manual:
	docker compose --profile test run --rm -v "$$PWD/backend:/app" -v "$$PWD/docs:/docs" -v "$$PWD/frontend/public:/frontend-public:ro" -v "$$PWD/docs/manual:/manual-out" -e MANUAL_OUT=/manual-out/RedShadow-User-Manual.pdf -e BRAND_DIR=/frontend-public/brand -e APP_VERSION="$${APP_VERSION:-1.4.0}" backend-test python /docs/manual/build_manual.py

# Writes docs/openapi.json (drf-spectacular, dev-only settings). A typed client can be generated from it with openapi-typescript.
schema:
	docker compose --profile test run --rm -v "$$PWD/backend:/app" -v "$$PWD/docs:/schema-out" -e DJANGO_SETTINGS_MODULE=config.settings.schema backend-test python manage.py spectacular --file /schema-out/openapi.json --format openapi-json
