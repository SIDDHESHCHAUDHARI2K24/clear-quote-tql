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

### Getting started

1. Start Kaneo locally at `http://localhost:5183`. The Kaneo MCP is preconfigured for all agents.
2. Run backlog item CQ-001 (`docs/backlog/CQ-001-agent-tooling/spec.md`) to set up the coding agents.
3. Add the data-field catalog as `docs/design/data-field-catalog.md`.
4. Work through the backlog in wave order (`docs/roadmap.md`).
