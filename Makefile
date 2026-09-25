.PHONY: up down logs lint test api-client demo-reset

# Local stack (Postgres, Valkey, MinIO, Mailpit, Temporal). Real compose file
# lands in CQ-003; until then this fails loudly (docker compose errors on the
# missing file) instead of doing nothing.
up:
	docker compose -f infra/docker-compose.yml up -d --wait

down:
	docker compose -f infra/docker-compose.yml down

logs:
	docker compose -f infra/docker-compose.yml logs -f

lint:
	uv run ruff check backend
	uv run ruff format --check backend
	uv run mypy backend/app
	pnpm -r run lint
	pnpm -r run typecheck
	pnpm exec prettier --check .

test:
	uv run pytest backend
	pnpm -r run test

# CQ-004 adds backend/scripts/export_openapi.py, which overwrites
# packages/api-client/openapi.json with the real app.openapi() export. Until
# it exists, this target uses CQ-005's hand-written stub (GET /health only,
# in the exact shape pinned by CQ-004's spec.md) so the frontend can still
# generate a typed client. No further Makefile edit is needed once CQ-004
# lands: this step just starts finding the script.
api-client:
	@if [ -f backend/scripts/export_openapi.py ]; then \
		uv run python backend/scripts/export_openapi.py; \
	else \
		echo "api-client: backend/scripts/export_openapi.py not found yet (CQ-004) -- generating from the packages/api-client/openapi.json stub instead"; \
	fi
	pnpm --filter @cq/api-client run generate

# CQ-010 replaces this body with the real demo reset (drop DB, migrate, seed).
demo-reset:
	@echo "demo-reset: not implemented until CQ-010"

# make api    -- added by CQ-004: uv run uvicorn app.main:app --port 8000 --reload
# make worker -- added by CQ-011: cd backend && uv run python -m app.workflows.worker
