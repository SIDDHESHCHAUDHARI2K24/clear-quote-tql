# CQ-030 Stale quote job

| Field | Value |
| --- | --- |
| Phase | P5 LO Tier B |
| Depends on | CQ-011 |
| Kaneo task | CQ-030 in Kaneo (task id `vx3bu30y7asxddivv7ao4kv2`) |
| Branch | `cq-030-stale-quote-job` |
| Status | Approved 2026-09-25 (`spec-ready` in Kaneo) |

## Goal

Rates move, so quotes expire. After 21 days the system marks quotes stale on its own, the LO sees it, the borrower's report says the numbers have expired, and one click re-prices.

## Scope

**Backend (owned by this item)**

- A Temporal Schedule `stale-quote-check` that runs every hour (interval from settings; 1 minute allowed in dev for demos). It runs the activity `mark_stale(now)`:
  1. Quotes with `priced_at < now − stale_days` (default 21) → `stale = true`.
  2. Sent versions with `expires_at < now` → `expired` state (the borrower report computes it too; this makes it queryable).
  3. Applications in Priced, Sent or Viewed whose recommended quote or latest sent version is stale/expired → status Stale, with one activity event "Quotes older than 21 days". Applications in Inquiry or OptionSelected keep their status but their quotes are flagged stale.
  4. Idempotent: a second run changes nothing and writes no events.
- `now` is injected (settings override `CLOCK_NOW` in tests and demos), never read directly inside the activity.
- Re-price from Stale: the CQ-018 `POST /api/applications/{id}/reprice` moves Stale → Priced when it succeeds (adapt to the built endpoint).
- The worker registers the schedule on startup if it does not exist.

## Out of scope

- The Stale UI surfaces: dashboard list (CQ-025), expired banner (CQ-022), re-price button (CQ-018) already exist or are specified there.
- The admin "run now" button lives in CQ-029 and calls `POST /api/admin/jobs/stale-check`, which this item implements.

## References

- `docs/design/system-design.md` — Application status machine (Stale transitions), Automation-first input model.
- Built code to check in stage 1: CQ-011 workflow/worker setup, CQ-018 reprice endpoint, CQ-022 `expired` computation.

## Acceptance criteria

- [ ] AC1 — After `make demo-reset`, one run marks Grace Kim's quote stale and her status Stale, and writes exactly one activity event.
- [ ] AC2 — A second run makes no changes and writes no events.
- [ ] AC3 — With `CLOCK_NOW` set to 22 days after Marcus Hale's send, his status becomes Stale and his report shows expired; at 20 days, nothing changes.
- [ ] AC4 — An application in OptionSelected keeps its status; its quotes are flagged stale.
- [ ] AC5 — Re-pricing Grace Kim moves her to Priced with fresh `priced_at` and clears the stale flags.
- [ ] AC6 — The schedule exists in Temporal after the worker starts (visible in Temporal UI) and survives a worker restart without duplicating.
- [ ] AC7 — `POST /api/admin/jobs/stale-check` runs the same activity and returns the counts changed; non-admins get 403.

## Test plan

| Criterion | Test type | Test name / command |
| --- | --- | --- |
| AC1, AC2 | Activity tests on seed | `test_mark_stale_grace_kim`, `test_mark_stale_idempotent` |
| AC3 | Activity test with injected clock | `test_mark_stale_clock_boundaries` |
| AC4 | Activity test | `test_option_selected_keeps_status` |
| AC5 | API test | `test_reprice_clears_stale` |
| AC6 | Temporal test env | `test_schedule_registered_once` |
| AC7 | API test | `test_admin_stale_check_endpoint` |

## Notes for the agent

- Keep the boundary rule strict: stale when age is strictly greater than 21 days.
- Follow the agent loop in `AGENTS.md`. Log small decisions in `plan.md`; raise big gaps in Kaneo.
