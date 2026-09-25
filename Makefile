.PHONY: up down logs lint test api api-client demo-reset worker

# Local stack (Postgres, Valkey, MinIO, Mailpit, Temporal), project name
# `clear-quote` (infra/docker-compose.yml). --wait blocks until every
# service with a healthcheck reports healthy (or minio-init exits 0).
up:
	docker compose -f infra/docker-compose.yml up -d --wait

down:
	docker compose -f infra/docker-compose.yml down

logs:
	docker compose -f infra/docker-compose.yml logs -f

lint:
	uv run ruff check backend
	uv run ruff format --check backend
	uv run mypy backend/app backend/conftest.py backend/tests backend/scripts
	pnpm -r run lint
	pnpm -r run typecheck
	pnpm exec prettier --check .

test:
	uv run pytest backend
	pnpm -r run test

# backend/scripts/export_openapi.py (CQ-004) overwrites
# packages/api-client/openapi.json with the real app.openapi() export, then
# openapi-typescript regenerates the typed client from it.
api-client:
	uv run python backend/scripts/export_openapi.py
	pnpm --filter @cq/api-client run generate

# CQ-010 replaces this body with the real demo reset (drop DB, migrate, seed).
demo-reset:
	@echo "demo-reset: not implemented until CQ-010"

# Dev server, port 8000 is pinned for this project (CQ-004).
api:
	uv run uvicorn app.main:app --port 8000 --reload

# Temporal worker: registers ApplicationPipelineWorkflow + activities on
# the pipeline task queue (CQ-011). Requires `make up` (Temporal at
# localhost:7233) to be running first.
worker:
	cd backend && uv run python -m app.workflows.worker
