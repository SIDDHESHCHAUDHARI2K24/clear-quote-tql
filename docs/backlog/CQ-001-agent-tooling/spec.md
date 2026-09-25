# CQ-001 Agent tooling & process

| Field | Value |
| --- | --- |
| Phase | P0 Foundations |
| Depends on | none |
| Kaneo task | CQ-001 in Kaneo (task id `oc4kzxbpmzryhmnc4k5s0mav`) |
| Branch | `cq-001-agent-tooling` |
| Status | Ready — the human runs this item together with the agent, because installs touch user-level config |

## Goal

Any of the three coding agents (Claude Code, Codex CLI, OpenCode) can open this repo and immediately have the same instructions, the superpowers skills, codegraph and graphify, and the Kaneo MCP. Every later backlog item depends on this.

## Scope

1. Shared instructions: `AGENTS.md` (already in the repo) is the single source; `CLAUDE.md` contains only `@AGENTS.md`.
2. Superpowers for all three agents, project-scoped where the agent supports it.
3. codegraph wired into all three agents, project index built.
4. graphify installed for all three agents (project scope), non-strict mode, git hooks installed.
5. Kaneo MCP (`@kaneo/mcp serve`, stdio) configured for all three agents against the local Kaneo at `http://localhost:5183`. No API key.
6. react-doctor skill available for frontend items.
7. Backlog process files (already in `docs/backlog/`) verified against the Kaneo project.

## Out of scope

- Application code, Makefile, Docker Compose (CQ-001, CQ-002).
- Any secret committed to git.

## Prerequisites (human)

git, Docker, Node 22+ with pnpm, Python 3.12 with uv, Claude Code, Codex CLI, OpenCode. Kaneo running locally at `http://localhost:5183`.

## Steps

Install commands come from each project's README as of 2026-09-24. **Re-read each README before running**; if a command changed, follow the README and log it as a `Decision:` in `plan.md`.

### 1. Superpowers ([obra/superpowers](https://github.com/obra/superpowers))

| Agent | Install | Scope |
| --- | --- | --- |
| Claude Code | `/plugin marketplace add obra/superpowers-marketplace`, then `/plugin install superpowers@superpowers-marketplace`. Commit the resulting `enabledPlugins` / marketplace entries in `.claude/settings.json` | Project |
| Codex CLI | `/plugins` → search "superpowers" → Install Plugin | User (one-time; documented in AGENTS.md) |
| OpenCode | Ask OpenCode: "Fetch and follow instructions from https://raw.githubusercontent.com/obra/superpowers/refs/heads/main/.opencode/INSTALL.md". Target the project `opencode.json` where the instructions allow | Project where supported |

### 2. codegraph ([colbymchenry/codegraph](https://github.com/colbymchenry/codegraph))

```bash
curl -fsSL https://raw.githubusercontent.com/colbymchenry/codegraph/main/install.sh | sh
# new terminal
codegraph install --target=claude,codex,opencode --location=local --yes
codegraph init
codegraph status
```

`.codegraph/` is already gitignored. The installer writes a fenced section into `AGENTS.md`/`CLAUDE.md`; keep it below the marker line.

### 3. graphify ([Graphify-Labs/graphify](https://github.com/Graphify-Labs/graphify))

```bash
uv tool install graphifyy          # package is graphifyy (double y)
graphify install --project --platform claude
graphify install --project --platform codex
graphify install --project --platform opencode
graphify claude install
graphify codex install
graphify opencode install
graphify hook install
graphify extract . --code-only     # first graph without an LLM key; docs get added later via /graphify
```

- Non-strict mode only (do not pass `--strict`).
- Add `graphify-out/` to `.claudeignore`; `graphify-out/cost.json` is already gitignored; commit the rest of `graphify-out/`.
- Codex: add `multi_agent = true` under `[features]` in `~/.codex/config.toml`.
- After both tools have written their sections, move the **Tool split** section of `AGENTS.md` so it stays above the generated sections (it already is, unless an installer prepended).

### 4. Kaneo MCP

Kaneo runs locally, so no URL secret or API key is needed. The configs are already committed; this step only verifies them.

| Agent | File (committed) | Entry |
| --- | --- | --- |
| Claude Code | `.mcp.json` | `kaneo`: `npx -y @kaneo/mcp serve`, env `KANEO_API_URL=http://localhost:5183` |
| Codex CLI | `.codex/config.toml` (project; copy to `~/.codex/config.toml` if your Codex ignores project config) | `[mcp_servers.kaneo]` same command and env |
| OpenCode | `opencode.json` | `mcp.kaneo`: `type: local`, same command, `environment.KANEO_API_URL`, `enabled: true` |

If an installer (codegraph, graphify, superpowers) rewrites one of these files, keep the `kaneo` entry intact.

### 5. react-doctor

Install the react-doctor skill for all three agents following its own README, project scope where supported. If it is not available for an agent, log a `Decision:` and note the fallback (run it from Claude Code only).

### 6. Process check

- `docs/backlog/README.md` lists 36 items; Kaneo project "Clear Quote TQL" has 36 tasks with matching titles.
- Add a short "Setup" section to `README.md` (repo root) with the prerequisites and the local Kaneo requirement.

## Acceptance criteria

- [ ] AC1 — In a fresh Claude Code session: superpowers skills are listed, `codegraph_explore` is available, `graphify query "backlog workflow"` returns results, and the agent can read CQ-001 in Kaneo and add a comment.
- [ ] AC2 — Same four checks pass in a fresh Codex CLI session.
- [ ] AC3 — Same four checks pass in a fresh OpenCode session.
- [ ] AC4 — `.mcp.json`, `.codex/config.toml` and `opencode.json` each contain the `kaneo` entry after all installers have run, and each agent lists the Kaneo tools.
- [ ] AC5 — `AGENTS.md` keeps the Tool split, Agent loop, Handoff and Kaneo sections above any tool-generated sections; `CLAUDE.md` is exactly `@AGENTS.md` (plus any generated section below it).
- [ ] AC6 — react-doctor runs from at least Claude Code; availability for Codex and OpenCode is recorded in `post-dev.md`.

## Test plan

| Criterion | Test | Evidence |
| --- | --- | --- |
| AC1–AC3 | Manual session per agent with a fixed prompt: "List your skills, run a codegraph query for AGENTS.md, run graphify query 'backlog workflow', read Kaneo task CQ-001 and comment 'tooling check'" | Transcript excerpt or screenshot per agent in `post-dev.md` |
| AC4 | `grep -n kaneo .mcp.json .codex/config.toml opencode.json`; tool list in each agent | Command output |
| AC5 | Read the files | Diff snippet |
| AC6 | `react-doctor` run on an empty page | Command output |

## Notes for the agent

- This item edits user-level config (`~/.codex/config.toml`, global CLI installs). Ask the human before each user-level change.
- Brainstorm stage: check that each README still matches the commands above; small differences → `Decision:`; a tool no longer supporting an agent → Kaneo `needs-input`.
