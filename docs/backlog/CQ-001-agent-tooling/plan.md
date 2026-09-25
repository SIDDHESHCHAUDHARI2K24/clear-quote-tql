# CQ-001 — Implementation plan

Written by the agent in stages 1–3. Do not start coding until every acceptance criterion maps to a test.

## Decisions & questions (stage 1)

| # | Type | Item | Resolution |
| --- | --- | --- | --- |
| 1 | Decision | Verify-only mode | Decided: Claude Code only; Codex CLI and OpenCode checks skipped per human decision on 2026-09-24 |
| 2 | Decision | codegraph install target | Decided: --target=claude --location=local (project-level) as per spec |
| 3 | Decision | graphify code+docs extraction | Decided: AST extraction (`code_files`) covers the 3 config files; for AC1's `graphify query "backlog workflow"` a small representative doc subset (`docs/backlog/README.md`, `docs/roadmap.md`, `AGENTS.md`'s agent-loop/Kaneo sections) was semantically extracted by hand, with the host agent as the LLM per graphify's own SKILL.md ("otherwise the host agent itself is the LLM" — no API key set). Full corpus semantic extraction (153 doc files) is deferred to a later `/graphify` run, matching the spec's "docs get added later via /graphify" |
| 4 | Decision | Removed stray backup | `.claude/settings.json.graphify-bak` was staged by the prior agent; removed from git and disk — not a real config file |
| 5 | Decision | Portability fix | `.claude/settings.json` PreToolUse hooks referenced an absolute, user-specific path (`/Users/siddheshc2001gmail.com/.local/bin/graphify`); changed to bare `graphify` (PATH-resolved) so the committed config works for any contributor whose `uv tool install` puts `graphify` on `PATH` |
| 6 | Decision | graphify-out/cache/ gitignored | The AST/query cache under `graphify-out/cache/` is a regenerable, machine/timing-dependent artifact (mtimes, stat index) with no review value; added to `.gitignore` rather than committed. `graphify-out/graph.json`, `manifest.json`, `GRAPH_REPORT.md`, `.graphify_analysis.json`, `.graphify_root` are committed per spec |
| 7 | Decision | graphify hook install skipped | `graphify hook install` writes the post-commit/post-checkout hooks into `.git/hooks` as expected, but also creates a tracked `.gitattributes` (`graphify-out/graph.json merge=graphify`) and registers a `merge.graphify.driver` in local git config — outside the "only writes .git/hooks" bound set for this verify-only pass. Ran install then uninstall to confirm both behaviors and left it uninstalled; a future item can opt in explicitly |

## Why

Agent tooling foundation enables all downstream work (CQ-002 onward). Verify tooling is installed and functional in Claude Code.

## What changes

| Area | Files (create / modify) |
| --- | --- |
| Setup | README.md (add Setup section with prerequisites) |
| Verification | plan.md, post-dev.md (fill with evidence) |
| Tooling | .mcp.json, .claude/settings.json, CLAUDE.md, .codegraph/, graphify-out/ |
| Git | Commit tooling setup in worktree branch |

## Tasks

| Task | Description | Depends on | Owned files | Test(s) |
| --- | --- | --- | --- | --- |
| T1-Codegraph | Install codegraph project-level; verify MCP entry in .mcp.json | — | .mcp.json, .codegraph/, .claude/settings.json | AC4 |
| T2-Graphify | Install graphify project-level; extract graph; verify query works | — | graphify-out/, .claude/CLAUDE.md | AC4 |
| T3-Verify | Verify superpowers, react-doctor; update README with Setup | T1, T2 | README.md, post-dev.md | AC1, AC6 |

## Wave schedule (stage 3)

| Wave | Tasks (run in parallel) | Why this order |
| --- | --- | --- |
| 1 | T1-Codegraph, T2-Graphify | Independent; no file conflicts |
| 2 | T3-Verify | Requires T1 and T2 complete |

## Acceptance → test map

| Criterion | Test |
| --- | --- |
| AC1 | superpowers listed, codegraph_explore available, graphify query works, Kaneo readable (Claude Code verified) |
| AC2 | Codex CLI checks (skipped) |
| AC3 | OpenCode checks (skipped) |
| AC4 | kaneo entry in .mcp.json; codegraph and graphify MCPs listed (verified) |
| AC5 | AGENTS.md structure preserved; CLAUDE.md is @AGENTS.md + generated sections (verified) |
| AC6 | react-doctor --help runs successfully (verified) |

## Progress

- [x] T1-Codegraph: codegraph install --target=claude --location=local --yes (idempotent, "Unchanged"); codegraph init; codegraph status (0 files — no app code exists yet, expected pre-CQ-002); verified .mcp.json has kaneo entry
- [x] T2-Graphify: graphify install --project --platform claude; AST extraction over the 3 code config files (20 nodes) + hand-authored semantic extraction over 3 representative docs (6 nodes) merged into graphify-out/graph.json (26 nodes, 25 edges, 5 communities); `graphify query "backlog workflow"` returns 7 nodes / 7 edges; cleaned up cache and settings.json portability fix; graphify hook install/uninstall verified, left uninstalled (Decision 7)
- [x] T3-Verify: superpowers confirmed in ~/.claude/plugins/installed_plugins.json (superpowers@claude-plugins-official 6.4.1); react-doctor@latest --help runs; README.md Setup section added
