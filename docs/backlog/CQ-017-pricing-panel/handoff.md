# CQ-017 — Handoffs

Append one entry per handoff, newest at the bottom. A new session reads spec.md, plan.md, then the latest entry.

## Handoff 1 — 2026-09-25 — Sonnet 5 (Claude Code)

- **Branch / last commit:** `cq-017-pricing-panel` @ (this handoff's own commit, `CQ-017: wip: ...` — see `git log -1`)
- **Stage:** 6 Review (multiple automated review passes addressed; no fresh-subagent `code-review`/PR review has run yet) — functionally the item is feature-complete and all local gates are green; stopping here only because of a session context-budget rule from the human (max ~400K context per agent), not because of open work.
- **Done:**
  - Full implementation per spec.md AC1-AC8: backend `GET /applications/{id}/pricing` (new `pricing/panel/**`), stale-marking on override/revert (`pricing/enrichment/service.py`), `/quotes/preview` accepting either side of the down-payment %/$ link + staff auth (`pricing/scenarios/{router,schemas}.py`), two new `quote_engine.py` functions (`down_payment_pct_from_amount`, `insurance_annual_rate_from_amount`) plus a new `QuoteComputation.down_payment_pct` field.
  - Frontend `apps/lo-console/src/features/pricing/**`: `PricingPanel`, `DownPaymentLinkedInput`, `EnrichedMoneyField`/`EnrichedPercentField`, `QuoteBuilderSlot` (CQ-018's stale banner + placeholder), `usePricingPreview` (debounced live preview), a no-money-math scan test, 5 component/hook test files (25 tests), 5 captured-shape fixtures.
  - `e2e/lo-console/pricing-panel.spec.ts` (6 tests) + `pricing-latency.spec.ts` (1 test, AC7 p95=380ms) — all passed against a real running stack (slot 5) after a fresh `make demo-reset`. Screenshot evidence captured.
  - `docs/backlog/CQ-017-pricing-panel/{plan,post-dev}.md` fully written (31 logged decisions/findings in plan.md; deviations, acceptance evidence, review findings, response shape, stale-marking explanation, live-verification transcript in post-dev.md).
  - `docs/backlog/README.md`'s CQ-017 row set to "In Review".
  - `make lint` and `make test` both fully green as of this handoff (backend 425, seed 27, frontend 215 — see post-dev.md's Test log for the exact breakdown).
  - `graphify update .` run (twice — once after the first pass, once after the review-round fixes).
  - Addressed a large multi-angle automated review relay (8 passes) from the orchestrator: all MUST-FIX correctness/AGENTS.md-compliance findings fixed (money math moved into `quote_engine`, two 500-vs-422 guards, a stale-marking race, a batched query, an always-logged activity event, `down_payment_pct` moved onto `QuoteComputation` itself); several quality findings logged as deliberately-not-fixed in plan.md (#24-31) with reasoning.
- **In progress:** Nothing mid-edit — every file is in a consistent, tested, committed-at-this-handoff state. The only "unfinished" items are the explicitly-logged follow-ups in plan.md #24-31 (see below), none of which block the acceptance criteria.
- **Next 3 steps:**
  1. Run the `code-review` skill (or the phase orchestrator's fresh-subagent PR review) against the full diff one more time to confirm no new findings, then `git push` + `gh pr create --base phase-p3-p4 --head cq-017-pricing-panel` (title `CQ-017: ...`, body ending with the standard Claude Code footer) per the original task's stage-8 instructions.
  2. Post the Kaneo comment (task id `lky9qv864ao119rajk7ujqd8`) with the PR link and move it to `in-review` status — this was **not done yet** in this session (only the local repo work is complete).
  3. Consider the logged-not-fixed items in plan.md #24-31 if a later session has budget: the `FIELD_CONFIG`-driven `PricingPanel` refactor (#28), the "Unsaved — preview only" + Reset UX marker (#31), and a `_field_views` "not yet enriched" placeholder (#30) are the most user-visible of the deferred items, though none are required by spec.md's ACs.
- **Open questions / blockers:** None blocking. Two pre-existing, out-of-scope a11y findings are excluded from `pricing-panel.spec.ts`'s AC8 axe assertion with a documented reason (a `StatusPill` colour-contrast ratio and a `Card` h1→h3 heading jump, both `packages/ui`/CQ-016 owned) — see that spec file's comment and plan.md Decision 15.
- **Verify state:**
  ```
  cd <this worktree>
  uv run pytest backend -q          # expect 425 passed
  uv run pytest seed -q             # expect 27 passed
  pnpm -r run test                  # expect 215 passed across 4 packages
  make lint                         # expect all clean
  pnpm exec tsc --noEmit -p tsconfig.json   # e2e typecheck, expect clean
  ```
  For the E2E suite (needs the local stack up and a fresh `make demo-reset` against slot 5 or your own slot):
  ```
  bash scripts/worktree-env.sh 5   # or your own slot
  uv run alembic upgrade head && make demo-reset
  # in the background: uv run uvicorn app.main:app --app-dir backend --port <API_PORT>
  #                     uv run python -m app.workflows.worker
  #                     pnpm --filter @cq/lo-console exec next dev -p <LO_PORT>
  SEED_STAFF_PASSWORD=<slot's> LO_BASE_URL=http://localhost:<LO_PORT> PORTAL_BASE_URL=http://localhost:<PORTAL_PORT> \
    pnpm exec playwright test e2e/lo-console --workers=1
  # expect 18 passed (11 pre-existing + 7 this item's)
  ```
