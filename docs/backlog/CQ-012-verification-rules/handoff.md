# CQ-012 — Handoffs

Append one entry per handoff, newest at the bottom. A new session reads spec.md, plan.md, then the latest entry.

## Handoff 1 — 2026-09-25 — Claude (implementation agent, review-round-1 fixes)

- **Branch / last commit:** `cq-012-verification-rules` @ (fix commit, pushed after this entry — see `post-dev.md`'s CI log for the exact hash/run id)
- **Stage:** 8 Commit — CQ-012 itself is complete (all 6 ACs pass, review round 1 findings addressed). This entry exists for the item(s) that consume `run_and_persist`, not because CQ-012 has unfinished work.
- **Done:** All review round 1 findings fixed — `run_and_persist` no longer writes `activity_events` (returns `service.VerificationRunResult` instead); flags now auto-resolve when their rule passes again (`resolve_flag`); `ssn_format`/`dob_format` validate the co-borrower too (distinct `field_key`s); added boundary tests, a real `Quote.computed`-backed test, and a DB-decrypt-roundtrip test. `spec.md` line ~71 updated to match (orchestrator-authorised).
- **In progress:** Nothing — CQ-012 is done.
- **Open questions / blockers (for CQ-011 and CQ-013, not CQ-012):**
  1. **CQ-011's `verify_application` activity** must build its own `activity_events` row(s) from `run_and_persist`'s return value (`VerificationRunResult.rule_results`/`.auto_fixed`/`.flags_raised`/`.flags_resolved`) — CQ-012 deliberately writes none, to avoid conflicting with CQ-011 spec.md AC5's exact per-stage row count (see plan.md decision #11).
  2. **CQ-013's pricing service**, when it calls `evaluate_rules` directly with a freshly-computed `ScenarioSnapshot` (per this item's spec.md "Two run times" section), should also use `write_flag`/`resolve_flag` symmetrically (raise on fail, resolve on pass) rather than only ever calling `write_flag` — otherwise a DTI/assets flag that later clears (e.g. after the LO adds an asset) will never resolve on the pricing-stage path even though the Verify-stage path (`run_and_persist`) now does.
- **Next 3 steps:** None for CQ-012. For whoever starts CQ-011/CQ-013: read the two bullets above before wiring `run_and_persist`/`write_flag`/`resolve_flag` in.
- **Verify state:** `make up && cp .env.example .env && uv run pytest backend/app/features/applications/verification -q` (31 tests) then `uv run pytest backend -q` (full suite).
