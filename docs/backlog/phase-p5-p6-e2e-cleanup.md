# P5/P6 e2e cleanup (slot 27)

Makes the full lo-console + borrower-portal + cross-app Playwright suite
order-independent under `--workers=1`. Before this, the two files named by
the coordinator (`dashboard-tiles.spec.ts`, `applications-list.spec.ts`)
had known failures, and nobody had actually run the **full** cross-app
suite (lo-console, borrower-portal and cross-app in one pass) -- prior
verification (e.g. CQ-029's post-dev.md "Review round 1") only ran
`e2e/lo-console` alone. Running the full suite surfaced several more
cross-spec leaks between specs that share a seeded persona.

## Failures found, root causes, fixes

### 1. `e2e/lo-console/dashboard-tiles.spec.ts` (CQ-025) -- named leak

AC5's test resolved Aisha Coleman's `flags`/`applications` rows directly
in Postgres, as a stand-in for CQ-028's real re-verify endpoint before
CQ-028 existed. CQ-028 has since merged and added
`e2e/lo-console/aisha-occupancy-resume.spec.ts`, which covers the same AC
through the real UI and pipeline. The DB-mutation test was removed
outright (not restored) -- its comment now points at the real spec.

### 2. `e2e/lo-console/applications-list.spec.ts` (CQ-027) -- named leak

`getByRole('button', { name: /^Status/ })` matched two buttons once
CQ-027 and the table both existed: the filter bar's `Status` `MultiSelect`
trigger ("Status Any") and `ApplicationsTable`'s sortable "Status" column
header. Added a scoped `applicationsFilterBar(page)` helper (an xpath
ancestor lookup from the `Search` field to the filter bar's own root div)
and routed both `Status`-button locators through it.

### 3. `aisha-occupancy-resume.spec.ts` leaking into 4 other specs

This file (CQ-028's real AC1 test) permanently resolves Aisha Coleman's
blocking flag and prices her application -- correct and intentional, but
it runs first alphabetically in `e2e/lo-console`, so every other spec that
still asserts her *original* seeded state (`needs_attention`, missing
occupancy) failed once it ran: `dashboard-tiles.spec.ts`'s AC3,
`workspace.spec.ts`'s AC4, `applications-list.spec.ts`'s status-filter
test, and `portal-home.spec.ts`'s AC1/AC2 (borrower-portal, after the
lo-console project runs).

Fix: `aisha-occupancy-resume.spec.ts` now restores her state in
`test.afterAll` -- `applications.status`/`occupancy`/`last_pipeline_stage`/
`recommended_quote_id`, and un-resolves her `flags` row (`write_flag`/
`resolve_flag` only ever set `resolved_at`, never delete, so re-opening
the original row reproduces the exact original flag). Also had to reset
`updated_at` to `'epoch'` by hand: it's an ORM-level `onupdate`, not a DB
trigger, so raw SQL doesn't touch it, and the dashboard's "Needs your
attention" list is `updated_at.asc()` + `limit(10)` -- a stale-recent
timestamp silently sorted her out of the top 10.

### 4. `apply-wizard-resume.spec.ts` (CQ-032) and `portal-home.spec.ts`'s
own AC4 (CQ-031) both leak into `shell.spec.ts` (borrower-portal)

Both specs sign in as the one seeded "no application" borrower
(`noapp.borrower@clearquote-demo.test`, "Nadia") and leave a real, open
`application_drafts` row behind (one from typing into the wizard, one from
just loading `/apply`). `shell.spec.ts` signs in as the same persona later
and asserts "No application yet" specifically because she's meant to be
untouched. Fixed at the source in both files: each deletes its own open
draft (`submitted_application_id is null`) right after it's no longer
needed.

### 5. `workspace.spec.ts`'s AC6 (CQ-016) leaking into `portal-home.spec.ts`

AC6 withdraws Sam Reed's application (a real, terminal
`patch_application_status` call -- the whole point of the test). Later,
`portal-home.spec.ts`'s "pending credit-check consent" test inserts a
pending consent for Sam Reed and expects the task banner to render --  but
`stage_and_label` maps any `_CLOSED_STATUSES` application straight to
`next_action = NONE`, so a withdrawn Sam Reed can never show the banner
regardless of the consent row. Fixed: `workspace.spec.ts`'s AC6 test
restores his seeded status (`priced`) after asserting the withdrawal.
There's no real "un-withdraw" flow (it's terminal by design), so this is
a direct SQL restore, same as the other fixes here.

### 6. `move-forward.spec.ts`'s two tests (CQ-024) leaking into
`portal-home.spec.ts`'s AC6

Both tests move Priya Nair off `priced` for real (`option_selected`, then
`inquiry`), via `freeze_sent_version.py` plus the real move-forward/ask
flows. `portal-home.spec.ts`'s AC6 (375px and 1280px) needs her back at
`priced` ("Your loan officer is reviewing your numbers"). Fixed: a
`test.afterAll` restores `applications.status = 'priced'` once both tests
finish.

### Helper change

`e2e/helpers/db.ts` gained one export, `execSql(sql)`, wrapping the
existing (previously private) `psql()` write path -- used by every
`afterAll`/inline restore above instead of each file reinventing its own
`docker compose exec psql` helper (which is what the now-deleted
`dashboard-tiles.spec.ts` DB mutation used to do locally).

### Checked and ruled out (no fix needed)

- **Kathleen McReynolds** (`property-tab.spec.ts` flips her property from
  TBD to a specific address): `report-gallery.spec.ts`'s Kathleen section
  is static fixture data (`packages/ui/src/report/fixtures.ts`), not
  DB-driven, so it's unaffected. `report-matches.spec.ts` reads a
  `quote_package_versions` row frozen once in `global-setup.ts`, before
  `property-tab.spec.ts` runs -- `freeze_package_version`'s own comment:
  "matches are computed from the same recommended quote being frozen into
  this version, so they're frozen with it too... a later `make demo-reset`
  or listing change never changes an already-sent report." No leak.
- **`workspace.spec.ts`'s AC7** (pipeline banner timing): reproduced
  cleanly across all runs in this session; the CQ-029 post-dev.md's
  earlier note about this being flaky did not reproduce here.

## Reported, not fixed (real, pre-existing issue -- out of scope)

**`e2e/borrower-portal/shell.spec.ts:31`**, test "header, nav and footer
disclosures render; no horizontal scroll at 375 px" (line 55 specifically,
and likely the `/apply`/`/tasks/credit-check` stub-text checks in the loop
just below it) fails deterministically, in every run, regardless of test
order:

- It asserts an `h1` reading "Support" and the text "Built in CQ-034" on
  `/support`. The real page (`SupportForm.tsx`, built by CQ-034) renders
  `<h1>Get in touch</h1>` with no "Built in CQ-034" text anywhere --
  confirmed against `support.spec.ts`'s own passing assertion
  (`getByRole("heading", { name: "Get in touch" })`).
- `grep -rn "Built in CQ-0" apps/borrower-portal/src` finds nothing at
  all, so the same stub-text pattern for `/apply` ("Built in CQ-032") and
  `/tasks/credit-check/...` ("Built in CQ-033") is very likely stale too,
  though the test never reaches them (it fails at `/support` first).

This is a P5/P6-foundation-era test (its own header comment: "the shell,
signed in as the seeded no-application borrower... E6, E17") written
against placeholder/stub pages, never updated once CQ-032/033/034 replaced
those stubs with the real features. It isn't a cross-spec leak (it fails
identically in isolation) and isn't an app bug (the app is working as
CQ-034 designed it) -- it's a stale test that nobody had run in the full
cross-app suite before this session (prior verification, e.g. CQ-029's
"Review round 1", only ran `e2e/lo-console`). Deciding the *correct*
current copy to assert belongs to whoever owns CQ-032/033/034's specs, so
it's left unfixed here per the "if it looks like a real bug, report it"
instruction, rather than guessed at.

## Code review (fresh subagent, effort low)

Three findings, all fixed:

1. `workspace.spec.ts`'s Sam Reed status restore ran inline at the end of
   the AC6 test body instead of in `test.afterAll`, unlike every other fix
   above -- a failed/timed-out assertion earlier in that test would have
   skipped it, leaving him withdrawn for every later run until a fresh
   `make demo-reset`. Moved to `afterAll`.
2. `portal-home.spec.ts`'s AC4 draft cleanup had the same inline-vs-
   `afterAll` issue (the draft is created by `/apply` loading, before the
   test's own "Apply" heading assertion). Moved to a second `afterAll`
   (the file already had one, for `closeDbPool()`).
3. `aisha-occupancy-resume.spec.ts`'s flag restore un-resolved *every*
   resolved flag on her application, not just the seeded "missing
   Occupancy" one -- `validate_ob_required_fields` calls `resolve_flag` for
   every field in `ALWAYS_REQUIRED` on each successful pipeline run, so a
   future flag raised-then-resolved for some other field during the real
   pipeline this test triggers would have been incorrectly reopened too.
   Scoped the restore to the exact `(field_key, rule)` pair
   (`occupancy_type`, `ob_required_field`) instead.

Re-verified with two more full-suite runs after these fixes (below);
identical results to the pre-review runs.

## Final run counts

Two consecutive full-suite runs (`pnpm exec playwright test --workers=1`,
`LO_BASE_URL=http://localhost:3127 PORTAL_BASE_URL=http://localhost:3227`),
each after a fresh `make demo-reset` and API/worker restart (slot 27: API
8127, LO console 3127, portal 3227):

| Run | Passed | Failed | Did not run (serial-blocked by the 1 failure) |
| --- | --- | --- | --- |
| 1 | 59 | 1 (`shell.spec.ts:31`, reported above) | 2 |
| 2 | 59 | 1 (same, same line) | 2 |

62 total specs across `lo-console` (29), `borrower-portal` (32) and
`cross-app` (1). Both runs identical: everything in scope is green and
stable; the one remaining failure is the pre-existing, out-of-scope issue
above.

## Files touched (all under `e2e/`)

- `e2e/lo-console/dashboard-tiles.spec.ts` -- removed the stale DB-mutation
  AC5 test
- `e2e/lo-console/applications-list.spec.ts` -- scoped `Status` locator
- `e2e/lo-console/aisha-occupancy-resume.spec.ts` -- `afterAll` state
  restore
- `e2e/lo-console/workspace.spec.ts` -- restore Sam Reed's status after
  AC6
- `e2e/borrower-portal/apply-wizard-resume.spec.ts` -- delete its own
  draft in `afterAll`
- `e2e/borrower-portal/portal-home.spec.ts` -- delete its own AC4 draft
  inline
- `e2e/borrower-portal/move-forward.spec.ts` -- `afterAll` restore Priya
  Nair's status
- `e2e/helpers/db.ts` -- new `execSql` export

Not touched: `e2e/lo-console/clients-list.spec.ts` (doesn't exist yet --
owned by the parallel CQ-026 worker) and `e2e/lo-console/shell.spec.ts`
(also CQ-026-owned; distinct file from the borrower-portal `shell.spec.ts`
discussed above).
