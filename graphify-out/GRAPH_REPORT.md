# Graph Report - .  (2026-09-24)

## Corpus Check
- 3 files · ~0 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 26 nodes · 25 edges · 5 communities (4 shown, 1 thin omitted)
- Extraction: 96% EXTRACTED · 0% INFERRED · 4% AMBIGUOUS
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- Community 0
- Community 1
- Community 2
- Community 3
- Community 4

## God Nodes (most connected - your core abstractions)
1. `kaneo` - 5 edges
2. `kaneo` - 5 edges
3. `command` - 5 edges
4. `Backlog Workflow` - 4 edges
5. `Kaneo backlog tracking` - 3 edges
6. `codegraph` - 2 edges
7. `mcp` - 2 edges
8. `environment` - 2 edges
9. `Agent Loop` - 2 edges
10. `Roadmap` - 2 edges

## Surprising Connections (you probably didn't know these)
- `Kaneo backlog tracking` --semantically_similar_to--> `kaneo`  [AMBIGUOUS] [semantically similar]
  AGENTS.md → .mcp.json
- `Backlog Workflow` --conceptually_related_to--> `Agent Loop`  [EXTRACTED]
  docs/roadmap.md → AGENTS.md
- `Backlog Workflow` --references--> `Kaneo backlog tracking`  [EXTRACTED]
  docs/roadmap.md → AGENTS.md
- `Backlog Index` --references--> `Roadmap`  [EXTRACTED]
  docs/backlog/README.md → docs/roadmap.md

## Import Cycles
- None detected.

## Communities (5 total, 1 thin omitted)

### Community 0 - "Community 0"
Cohesion: 0.29
Nodes (6): KANEO_API_URL, codegraph, npx, codegraph, kaneo, @kaneo/mcp

### Community 1 - "Community 1"
Cohesion: 0.40
Nodes (6): Agent Loop, Kaneo backlog tracking, Backlog Index, Backlog Workflow, Roadmap, Suggested Execution Waves

### Community 2 - "Community 2"
Cohesion: 0.40
Nodes (5): KANEO_API_URL, enabled, environment, type, kaneo

### Community 3 - "Community 3"
Cohesion: 0.40
Nodes (5): command, @kaneo/mcp, npx, serve, -y

## Ambiguous Edges - Review These
- `kaneo` → `Kaneo backlog tracking`  [AMBIGUOUS]
  AGENTS.md · relation: semantically_similar_to

## Knowledge Gaps
- **14 isolated node(s):** `npx`, `@kaneo/mcp`, `KANEO_API_URL`, `codegraph`, `$schema` (+9 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **1 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **What is the exact relationship between `kaneo` and `Kaneo backlog tracking`?**
  _Edge tagged AMBIGUOUS (relation: semantically_similar_to) - confidence is low._
- **Why does `kaneo` connect `Community 2` to `Community 3`, `Community 4`?**
  _High betweenness centrality (0.173) - this node is a cross-community bridge._
- **Why does `kaneo` connect `Community 0` to `Community 1`?**
  _High betweenness centrality (0.160) - this node is a cross-community bridge._
- **Why does `command` connect `Community 3` to `Community 2`?**
  _High betweenness centrality (0.127) - this node is a cross-community bridge._
- **What connects `npx`, `@kaneo/mcp`, `KANEO_API_URL` to the rest of the system?**
  _14 weakly-connected nodes found - possible documentation gaps or missing edges._