.PHONY: up down logs lint test api api-client demo-reset worker e2e

# CQ-020: WeasyPrint (the letter PDF) loads Pango/cairo via dlopen. On macOS
# Homebrew puts them in /opt/homebrew/lib, which dyld doesn't search by
# default. The variable must be set inline on the `uv` command: make's
# recipe shell (/bin/sh) is SIP-protected and strips DYLD_* from its own
# environment, and so does every `#!/bin/sh` console script (e.g.
# .venv/bin/pytest) -- hence `uv run python -m pytest` below, not `uv run
# pytest`. Empty on Linux (CI installs the libraries with apt).
PDF_ENV := $(if $(filter Darwin,$(shell uname -s)),DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib,)

# Local stack (Postgres, Valkey, MinIO, Mailpit, Temporal), project name
# `clear-quote` (infra/docker-compose.yml). --wait blocks until every
# long-running service with a healthcheck reports healthy. `minio` now
# creates its own buckets at startup via MINIO_DEFAULT_BUCKETS (CQ-003 fix,
# follow-up to CQ-006 Decision #17), so the old one-shot `minio-init`
# service is gone and every service is a normal long-running --wait target.
up:
	docker compose -f infra/docker-compose.yml up -d --wait postgres valkey minio mailpit temporal temporal-ui

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
	$(PDF_ENV) uv run python -m pytest backend
	$(PDF_ENV) uv run python -m pytest seed
	pnpm -r run test

# backend/scripts/export_openapi.py (CQ-004) overwrites
# packages/api-client/openapi.json with the real app.openapi() export, then
# openapi-typescript regenerates the typed client from it.
api-client:
	uv run python backend/scripts/export_openapi.py
	pnpm --filter @cq/api-client run generate

# Drops/recreates cq_dev's public schema, migrates, seeds personas +
# background data + sample docs. Never touches cq_test or the temporal DB
# (separate databases on the same shared Postgres). Budget: under 60s (AC1).
demo-reset:
	uv run python -m seed.reset

# Dev server, port 8000 is pinned for this project (CQ-004).
api:
	$(PDF_ENV) uv run python -m uvicorn app.main:app --port 8000 --reload

# Temporal worker: registers ApplicationPipelineWorkflow + activities on
# the pipeline task queue (CQ-011). Requires `make up` (Temporal at
# localhost:7233) to be running first. Run from the repo root (like `api`
# above) so Settings' env_file=".env" (backend/app/core/config.py) resolves
# the repo-root .env instead of a nonexistent backend/.env (CQ-011 fix).
worker:
	$(PDF_ENV) uv run python -m app.workflows.worker

# Playwright (H3, docs/backlog/phase-p3-p4-foundation.md). Not part of
# `make test` -- CI has no running stack (API, worker, Next dev servers,
# Mailpit) for these to talk to. A worker runs this by hand per
# docs/backlog/phase-p3-p4-plan.md's "E2E recipe", with LO_BASE_URL and
# PORTAL_BASE_URL set to its own worktree slot's ports
# (scripts/worktree-env.sh <slot>).
e2e:
	pnpm exec playwright test
