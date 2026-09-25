@AGENTS.md

## graphify

graphify-out/ holds a knowledge graph of the docs. Follow the Tool split in AGENTS.md: codegraph for code questions, graphify for docs/spec questions.

- For docs questions, run `graphify query "<question>"`; use `graphify path "<A>" "<B>"` or `graphify explain "<concept>"` for relationships and concepts.
- Read graphify-out/GRAPH_REPORT.md only for a broad architecture review.
- After changing docs or code, run `graphify update .` to keep the graph current (AST-only, no API cost).
