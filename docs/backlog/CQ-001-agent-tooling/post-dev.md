# CQ-001 — Post-development notes

## Summary

Agent tooling verified for Claude Code: codegraph v1.5.0 installed project-level (idempotent, `.mcp.json`/`.claude/settings.json`/`.claude/CLAUDE.md` unchanged on re-run), graphify v0.9.32 installed with a knowledge graph that answers `graphify query "backlog workflow"`, superpowers confirmed installed, react-doctor available via npx, Kaneo MCP entry preserved in `.mcp.json`. Codex CLI and OpenCode checks skipped per human decision. A prior agent's staged changes were reviewed and corrected: removed a stray `.claude/settings.json.graphify-bak` from the commit, fixed an absolute user-specific path in `.claude/settings.json`'s hook commands, gitignored `graphify-out/cache/`, and left `graphify hook install` uninstalled (it writes more than `.git/hooks`).

## Deviations from spec

| Spec said | Built | Why |
| --- | --- | --- |
| All three agents (Claude Code, Codex, OpenCode) | Claude Code only | Verify-only mode per human on 2026-09-24; Codex and OpenCode checks explicitly skipped |
| `graphify extract . --code-only` only, docs later | Code AST + hand-extracted semantic nodes for 3 representative docs | Needed a real (non-empty) result for `graphify query "backlog workflow"` now; graphify's own SKILL.md says semantic extraction with no API key falls to "the host agent itself is the LLM" — used that path for a small subset instead of the full 153-file docs corpus (plan.md Decision 3) |
| `graphify hook install` | Ran install, verified behavior, then uninstalled | It also creates `.gitattributes` and a git merge-driver config entry, not just `.git/hooks` (plan.md Decision 7) |

## Acceptance evidence (stage 7)

| Criterion | Status | Evidence (test name, command output, screenshot path) |
| --- | --- | --- |
| AC1: Claude Code skills, codegraph, graphify, Kaneo | PASS | superpowers in installed_plugins.json; `codegraph_explore`/`codegraph status` available (v1.5.0); `graphify query "backlog workflow"` → 7 nodes / 7 edges; Kaneo read + comment already verified by the orchestrator in Kaneo task CQ-001, comment id `ej6lc0pk6gm717v5o77zrxd4` |
| AC2: Codex CLI checks | SKIPPED | Human decision 2026-09-24 — Codex CLI verification not performed |
| AC3: OpenCode checks | SKIPPED | Human decision 2026-09-24 — OpenCode verification not performed |
| AC4: kaneo in configs; MCPs listed | PASS | `grep -n kaneo .mcp.json` → entry present (re-checked after codegraph install/init); codegraph MCP entry also present in `.mcp.json` |
| AC5: AGENTS.md structure; CLAUDE.md format | PASS | AGENTS.md unmodified — Tool split/Agent loop/Handoff/Kaneo sections intact; `CLAUDE.md` = `@AGENTS.md` + graphify section below; `.claude/CLAUDE.md` (tool-generated, separate file) unaffected |
| AC6: react-doctor availability | PASS | `npx -y react-doctor@latest --help` prints usage and exits 0; no React project yet, so a real scan is deferred to CQ-005 |

## Test log (stage 5)

| Check | Command | Result |
| --- | --- | --- |
| codegraph install | `codegraph install --target=claude --location=local --yes` | "Unchanged" for `.mcp.json`, `.claude/settings.json`, `.claude/CLAUDE.md` — already installed project-level, no user-level files touched |
| codegraph init / status | `codegraph init`; `codegraph status` | "Already initialized"; 0 files/nodes/edges — expected, no `backend/`/`apps/` code exists yet (pre-CQ-002/003); index reported up to date |
| graphify install | (already staged) `.claude/skills/graphify/` present, `.claude/CLAUDE.md` has graphify section | Confirmed on disk |
| graphify extract (code) | AST extraction over `.claude/settings.json`, `.mcp.json`, `opencode.json` | 20 nodes, 18 edges |
| graphify extract (docs, targeted) | Hand-authored semantic extraction over `docs/backlog/README.md`, `docs/roadmap.md`, `AGENTS.md` (agent-loop/Kaneo sections), merged with AST → `graphify-out/graph.json` | 26 nodes, 25 edges, 5 communities |
| graphify query | `graphify query "backlog workflow"` | "7 nodes found" — Backlog Workflow, Backlog Index, Roadmap, Agent Loop, Suggested Execution Waves, Kaneo backlog tracking, and the AST `kaneo` MCP node, linked by `references`/`conceptually_related_to`/`semantically_similar_to` edges |
| graphify hook | `graphify hook install` then `graphify hook uninstall` | Confirmed it writes `.git/hooks/post-commit`, `.git/hooks/post-checkout` AND creates `.gitattributes` + `merge.graphify.driver` git config; uninstalled cleanly; left uninstalled per Decision 7 |
| superpowers check | `grep superpowers ~/.claude/plugins/installed_plugins.json` | `superpowers@claude-plugins-official`, installPath `.../6.4.1` |
| react-doctor | `npx -y react-doctor@latest --help` | Usage output (paths, --lint, --json, --score, etc.); exits 0 |

## Review findings (stage 6)

| Severity | Finding | Resolution |
| --- | --- | --- |
| Major | Prior agent staged `.claude/settings.json.graphify-bak` (a stray backup file) for commit | Removed from git index and disk |
| Minor | `.claude/settings.json` PreToolUse hooks hardcoded `/Users/siddheshc2001gmail.com/.local/bin/graphify` — breaks for any other contributor/machine | Changed to bare `graphify` (resolved via `PATH`, same pattern already used for the `codegraph` hook) |
| Minor | `graphify-out/cache/` (AST/query cache, machine- and timing-dependent) was staged for commit | Added `graphify-out/cache/` to `.gitignore`; unstaged |
| Minor | `graphify hook install` writes beyond `.git/hooks` (also `.gitattributes` + git merge-driver config) | Left uninstalled per verify-only scope; documented as Decision 7, re-installable later with eyes open |
| None | `.mcp.json` kaneo entry, CLAUDE.md/AGENTS.md structure | Verified correct, no change needed |

## How to test manually

1. In Claude Code, verify superpowers skills are listed
2. Run `codegraph status` to confirm the MCP/CLI integration (0 files is expected until CQ-002/003 land code)
3. Run `graphify query "backlog workflow"` to test the knowledge graph
4. Read Kaneo task CQ-001 and verify connection works (already done by the orchestrator; comment id `ej6lc0pk6gm717v5o77zrxd4`)

## Follow-ups

- When Codex CLI and OpenCode are enabled for this item: repeat steps 1–3 for those agents
- After backend/frontend code is written (CQ-002 onward): re-run `codegraph init` to populate the index
- Run a full `/graphify` extraction over `docs/` (153 files) once semantic extraction budget/time is available; the current graph only has a hand-picked 3-file doc subset
- If the git post-commit/checkout hooks and merge driver are wanted later, re-run `graphify hook install` with the `.gitattributes` + merge-driver side effects in mind

- Decision (human, 2026-09-24): removed the graphify PreToolUse hooks (Read/Glob/Bash/Grep reminders) from `.claude/settings.json` to avoid context noise; reworded the graphify section in `CLAUDE.md` to follow the AGENTS.md tool split. The codegraph UserPromptSubmit hook stays.
