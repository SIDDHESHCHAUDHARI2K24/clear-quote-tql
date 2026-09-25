# Clear Quote TQL

Prototype of a mortgage quote and pre-approval experience for loan officers and borrowers, running on emulated provider data.

- Product and system design: `docs/design/system-design.md`
- Roadmap and backlog: `docs/roadmap.md`, `docs/backlog/`
- Agent instructions: `AGENTS.md`

## Setup

### Prerequisites

- **git** (version control)
- **Docker** (local services: Postgres, Valkey, MinIO, Mailpit, Temporal)
- **Node 22+** with **pnpm** (frontend and tooling)
- **Python 3.12** with **uv** (backend, Temporal)
- **Claude Code** (agent tooling; Codex CLI and OpenCode optional)
- **Kaneo** running locally at `http://localhost:5183` (backlog tracking; no API key needed)

### First run

1. `cp .env.example .env`, then fill in:
   - `FIELD_ENCRYPTION_KEY` — generate with:
     `uv run python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`
   - `SEED_STAFF_PASSWORD` — any local password; `make demo-reset` argon2-hashes it for the 4 seeded staff users and refuses to run if it's unset.
   - `SEED_BORROWER_PASSWORD` — optional; when set, `make demo-reset` also argon2-hashes it into a Borrower Portal account for every seeded persona client. Leave blank to skip borrower accounts.
   - The other variables have working local defaults already filled in.
2. `uv sync` — installs the backend (Python 3.12).
3. `pnpm install` — installs the frontends and shared packages.
4. `make up` — starts Postgres, Valkey, MinIO, Mailpit and Temporal (Docker).
5. `make demo-reset` — migrates the dev database and seeds personas + background data.
6. `make api` — runs the FastAPI backend on `:8000`.
7. `make worker` — runs the Temporal worker (needs `make up`'s Temporal at `localhost:7233`).
8. Frontends (each in its own terminal):
   - `pnpm --filter @cq/lo-console dev` — LO Console on `http://localhost:3010`
   - `pnpm --filter @cq/borrower-portal dev` — Borrower Portal on `http://localhost:3020`
9. `make lint` and `make test` before committing.

### Getting started

1. Start Kaneo locally at `http://localhost:5183`. The Kaneo MCP is preconfigured for all agents.
2. Run backlog item CQ-001 (`docs/backlog/CQ-001-agent-tooling/spec.md`) to set up the coding agents.
3. Add the data-field catalog as `docs/design/data-field-catalog.md`.
4. Work through the backlog in wave order (`docs/roadmap.md`).
