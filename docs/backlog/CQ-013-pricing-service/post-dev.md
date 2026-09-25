# CQ-013 Pricing service & API — post-dev

## Test log (stage 5)

Environment: local `clear-quote` compose stack (`make up`, already running — not stopped). `.env` copied from `.env.example` with `DEV_LO_ID` and a generated `FIELD_ENCRYPTION_KEY` added.

```
$ uv run pytest backend -q
........................................................................ [ 35%]
........................................................................ [ 70%]
.............................................................            [100%]
205 passed, 1 warning in 2.6s
```

(Baseline before this item, after merging phase-p0-p1 with CQ-012: 165 passed. This item adds 40 tests: 9 enrichment, 3 preview/perf, 5 auth-stub, 6 autoquote-selection, 4 DSCR two-pass, 4 OB-validation, 2 investment-default-scenarios, 3 primary-default-scenarios, 1 products-grid, 1 manual-quote, 2 draft-quote-set.)

Per-file (per spec.md's Test plan table):

```
$ pytest backend/app/features/pricing/scenarios/tests/test_quotes_preview_perf.py -q
3 passed in 0.10s
$ pytest backend/app/features/pricing/enrichment/tests/test_enrichment.py -q
6 passed in 0.20s
$ pytest backend/app/features/pricing/enrichment/tests/test_field_value_override.py -q
3 passed in 0.10s
$ pytest backend/app/features/pricing/scenarios/tests/test_ob_validation.py -q
4 passed in 0.17s
$ pytest backend/app/features/pricing/scenarios/tests/test_default_scenarios_investment.py -q
2 passed in 0.17s
$ pytest backend/app/features/pricing/scenarios/tests/test_default_scenarios_primary.py -q
3 passed in 0.19s
$ pytest backend/app/features/pricing/scenarios/tests/test_autoquote_selection.py -q
6 passed in 0.08s
$ pytest backend/app/features/pricing/scenarios/tests/test_dscr_two_pass_loop.py -q
4 passed in 0.13s
$ pytest backend/app/features/pricing/scenarios/tests/test_products_grid.py -q
1 passed in 0.16s
$ pytest backend/app/features/pricing/scenarios/tests/test_manual_quote.py -q
1 passed in 0.11s
$ pytest backend/app/features/pricing/scenarios/tests/test_auth_stub.py -q
5 passed in 0.08s
$ pytest backend/app/features/quotes/builder/tests/test_draft_quote_set.py -q
2 passed in 0.15s
```

Static checks:

```
$ uv run ruff check backend
All checks passed!
$ uv run ruff format --check backend
199 files already formatted
$ uv run mypy backend/app backend/conftest.py backend/tests backend/scripts
Success: no issues found in 199 source files
```

`make lint`'s frontend legs (eslint/tsc/prettier) were not run — this item touches no frontend code; `pnpm install` was run once to regenerate `packages/api-client` (see below).

```
$ make api-client
Wrote OpenAPI schema to .../packages/api-client/openapi.json
✨ openapi-typescript 7.13.0
🚀 openapi.json → src/schema.d.ts [25.9ms]
```

`make demo-reset` is still a stub (`echo "demo-reset: not implemented until CQ-010"`) — CQ-010 is in progress in a parallel worktree; not this item's gate.

## Acceptance checklist (stage 7)

| AC | Status | Evidence |
| --- | --- | --- |
| AC1 | Pass | `test_quotes_preview_perf.py` — 3/3 pass; explicit `elapsed_ms < 300` assertion (engine-only, no adapter, no persistence route). |
| AC2 | Pass | `test_enrichment.py` — 6/6 pass; covers tax/insurance/HOA/LTR-rent/STR-revenue sources and the overridden-field skip + idempotent-rerun cases. |
| AC3 | Pass | `test_field_value_override.py` — 3/3 pass; PATCH sets `overridden_by`/`overridden_at` + `source=lo_override`, POST `/revert` restores the source value and clears both, and an unknown `field_key` is 422. |
| AC4 | Pass | `test_ob_validation.py` — 4/4 pass; missing-field raises `PricingValidationError` with the pinned `Cannot price: missing <Field>` message/code/422, writes a `blocking` flag, resolves it once fixed (orchestrator's resolve-direction requirement), and the `/applications/{id}/scenarios` route itself surfaces the same 422 shape. |
| AC5 | Pass | `test_default_scenarios_investment.py` — 2/2 pass; collapsed single group when actual DSCR bucket matches the 1.00 assumption, two groups (with a working DSCR two-pass re-price) otherwise. |
| AC6 | Pass | `test_default_scenarios_primary.py` — 3/3 pass; one group at >=20% down, two groups (second Par-only at exactly 20%) at <20% down, and the no-argument default is 20%. |
| AC7 | Pass | `test_autoquote_selection.py` — 6/6 pass; par tie-break (abs points -> rate -> investor name), buydown <= 1.00-point selection, `None` when no row qualifies, and a `ValueError` when no row is marked par. |
| AC8 | Pass | `test_dscr_two_pass_loop.py` — 4/4 pass; converges pass 1, re-prices exactly once and converges pass 2, flip-flops to a `warning` flag keeping the lower-DSCR result, and a stable rerun resolves a previously-raised flag (orchestrator's resolve-direction requirement). |
| AC9 | Pass | `test_products_grid.py` — 1/1 pass; `GET /scenarios/{id}/products` returns 8-15 rows shaped exactly per the catalog's inbound fields, exactly one `is_par_rate`. |
| AC10 | Pass | `test_manual_quote.py` — 1/1 pass; persisted `quotes.computed` equals an independently-run `compute_quote` on the scenario's inputs with the picked row's rate/points. |
| AC11 | Pass | `test_auth_stub.py` — 5/5 pass; every route reachable with no `Authorization` header, `/quotes/preview` needs no DB/auth setup at all, and every route depending on the stub is 401 `AUTHENTICATION_ERROR` when `DEV_LO_ID` is unset. |
| AC12 | Pass | `ruff check` clean, `ruff format --check` clean, `mypy` clean (both the two owned packages and the whole backend). |

All 12 acceptance criteria pass with evidence above; no criterion needed a second pass.

## Decisions logged

See `plan.md`'s "Decisions & questions" (13 numbered decisions, including one bug fix caught mid-implementation: `PricedProductDTO.note_rate` is percent-scale while `ScenarioInputs.note_rate` is a 0-1 fraction — `dscr_loop.inputs_with_priced_product` is the single shared conversion point).

## Orchestrator update applied

CQ-012 merged into `phase-p0-p1` mid-task; branch fast-forward-merged it in. `write_flag`/`resolve_flag` (`app.features.applications.verification.service`) used with their real signatures — no shim was ever needed since the merge landed before that code was written. Both requested resolve-direction tests were added (see AC4/AC8 evidence above). Confirmed ownership boundary: `applications.service.import_from_los` is CQ-010's; this item owns `enrich_pricing_fields`, `validate_ob_required_fields`, `auto_price`, `draft_default_quote_set` — all four implemented under those exact names/paths.

## New contracts for downstream items (CQ-011, CQ-017/18, CQ-019/22)

- `pricing.enrichment.service.enrich_pricing_fields(db, application_id) -> EnrichmentResult`
- `pricing.enrichment.service.validate_ob_required_fields(db, application_id) -> bool` (raises `PricingValidationError`)
- `pricing.scenarios.service.auto_price(db, application_id) -> PricingResult(scenario_ids, quote_ids)`
- `pricing.scenarios.service.create_default_scenarios(db, application_id, down_payment_pct=None, prepayment_penalty_years=None) -> DefaultScenarioSetResult` — `auto_price` calls this with defaults; CQ-017/18's Quote Builder UI may re-invoke it with the LO's chosen down payment for a same-shaped re-price.
- `pricing.scenarios.service.create_scenario`, `autoquote_scenario`, `create_manual_quote`, `get_priced_products_for_scenario`, `select_par_and_buydown` — the Quote Builder's full server side.
- `quotes.builder.service.draft_default_quote_set(db, application_id, pricing_result) -> QuoteSetResult(quote_ids)` — **decision for CQ-019/22**: no recommendation is computed or persisted here (no table for it in this item's scope); Send-tab recommendation selection into `quote_packages.recommended_quote_id` is entirely CQ-019/22's job.
- `pricing.scenarios.dscr_loop.run_two_pass_dscr` / `TwoPassDscrResult` (includes `priced_at_dscr`, needed by any caller re-fetching that pass's full grid) and `pricing.scenarios.ob_request.build_ob_search_request` / `ObRequestOverrides`.
- New env var `DEV_LO_ID` (added to `Settings`, `.env.example`) — CQ-010 must seed a real `users` row with that exact id for the auth stub's FK-bearing writes (`field_values.overridden_by`) to work outside tests.
- Test-fixture note: `backend/app/features/pricing/conftest.py`'s `make_application` fixture seeds the "dev LO" user with `id = DEV_LO_ID` when set, so any future pricing test reusing it gets FK-consistent override/revert behavior for free.
- Shared test fixtures `_fake_valkey`/`_clean_integration_calls` moved from `backend/app/integrations/conftest.py` (deleted) up to `backend/conftest.py`, autouse repo-wide.

## Deviations from a literal reading of spec.md (all logged as Decisions in plan.md)

- No `settings`-table wiring into `ConfigSnapshot` (uses engine defaults everywhere) — no item has built that loader yet.
- `hoa_fee_monthly` is always `$0.00`/`DEFAULT` — no HOA data source exists anywhere in the merged codebase (catalog says Redfin/Zillow/listing, none modeled).
- `create_scenario` persists `quotes: []` (Decision 10) — quotes come from `/autoquote` or manual `/quotes`, matching the actual two-step Quote Builder UI, not literally the route table's naive reading.
- `draft_default_quote_set` does not compute a recommendation (Decision 11) — see contracts note above.

## Push + CI (stage 8)

- Commits: `5b58748` (CQ-013: feat: pricing service and API), `acdb6bc` (CQ-013: fix: default DEV_LO_ID in conftest so CI doesn't 401 pricing routes).
- Branch pushed: `cq-013-pricing-service` → `origin/cq-013-pricing-service`.
- CI run `5b58748`: **failed** (run id `36105244845`) — 6 tests 401'd because the GitHub Actions `backend` job's env block (CQ-006-owned) has no `DEV_LO_ID`, unlike my local `.env`. Root cause: I'd only set `DEV_LO_ID` in my own `.env`, not as a `conftest.py` `os.environ.setdefault(...)` default the way `APP_ENV`/`FIELD_ENCRYPTION_KEY`/`INTEGRATION_LATENCY_ENABLED` already are — so the suite wasn't actually self-contained yet.
- Fix (`acdb6bc`): added `os.environ.setdefault("DEV_LO_ID", "00000000-0000-0000-0000-000000000001")` to `backend/conftest.py`, matching the established pattern. Verified locally by running the full suite with `.env` moved aside and only the CI workflow's exact env vars set (`env -u DEV_LO_ID APP_ENV=test ... uv run pytest backend` — see command in the session) — 205 passed.
- CI run `acdb6bc`: **passed** (run id `36105462096`) — both `backend` and `frontend` jobs green.

## Review

Fresh-subagent review (stage 6). Verdict: **APPROVE** — no critical/major findings.

### Commands re-run

| Command | Result |
| --- | --- |
| `uv run pytest backend -q` | 205 passed |
| Per-file pytest for every AC1-AC11 test named in spec.md's test plan | all pass, counts match post-dev.md's log |
| Scratch test: `POST /quotes/preview` with `purchase_price=342000.00, down_payment_pct=0.20, note_rate=0.075` (i.e. $273,600 loan) | `loan_amount == 273600.00`, `monthly_pi == 1913.05` — golden confirmed through the actual API path, not just `compute_quote` directly (test written, run, and deleted; not part of the committed suite) |
| `uv run ruff check backend` | All checks passed |
| `uv run mypy backend/app backend/conftest.py backend/tests backend/scripts` | Success, no issues, 199 files |
| `make api-client` (after `pnpm install`, already present in worktree) | regenerated `openapi.json`/`schema.d.ts`; `git status --porcelain packages/api-client/` empty — committed artifact matches regeneration exactly |
| `git merge-tree --write-tree phase-p0-p1 HEAD` | clean tree (single hash, no conflict markers) |
| `git merge-tree --write-tree cq-010-seed-data HEAD` | clean tree (single hash, no conflict markers) — but see finding #1, a semantic (not file-level) contract mismatch git merge-tree cannot see |
| CI run `36105589880` (HEAD `dfe8f56`), `--log` | confirms `backend` job runs every pricing/enrichment/scenarios/quotes-builder test file individually (`test_enrichment.py`, `test_field_value_override.py`, `test_auth_stub.py`, `test_autoquote_selection.py`, `test_default_scenarios_investment.py`, `test_default_scenarios_primary.py`, `test_dscr_two_pass_loop.py`, `test_manual_quote.py`, `test_ob_validation.py`, `test_products_grid.py`, `test_quotes_preview_perf.py`); run conclusion `success` |

### Findings

| # | severity | file:line | finding | suggested fix |
| --- | --- | --- | --- | --- |
| 1 | major (cross-item, not a CQ-013 defect) | `seed/pricing_seam.py:66-69` (in the `cq-010-seed-data` worktree, not this branch) | CQ-010's Phase-A seam guesses call signatures `enrich_pricing_fields(application_id, db)`, `validate_ob_required_fields(application_id, db)`, `auto_price(application_id, db)`, `draft_default_quote_set(application_id, pricing_result, db)` — every one has `db` in the wrong position. CQ-013's real signatures (confirmed by reading the source) are `enrich_pricing_fields(db, application_id)`, `validate_ob_required_fields(db, application_id)`, `auto_price(db, application_id)`, `draft_default_quote_set(db, application_id, pricing_result)` — `db` always first, matching the rest of the codebase's convention. Since all args are positional, this will not raise `TypeError` at Phase-B flip time; it will bind `db=<UUID>` / `application_id=<AsyncSession>` and crash on first attribute access (e.g. `db.execute` on a UUID). CQ-010's own file comments already flag this as a "best-effort guess... reconcile against the real signature when wiring Phase B", so this is not a CQ-013 bug — it's the confirmation CQ-010 asked for. | CQ-010's owner reorders the four calls to `(db, application_id[, pricing_result])` when flipping `SEED_SKIP_PRICING`/wiring Phase B. No change needed on this branch. |
| 2 | minor | `docs/backlog/CQ-013-pricing-service/plan.md` Decision 4 / `spec.md` References | `ConfigSnapshot()` defaults are used everywhere (preview, scenario create, auto-price) rather than loading CQ-007's seeded `settings` table, even though system-design's data model says settings are "snapshotted into each scenario" so admin changes take effect for new quotes. This is a real, if currently unavoidable, gap (no item has built the settings→`ConfigSnapshot` loader yet) — correctly logged as Decision 4 and in the "Deviations" section, and every scenario still stores its own `config_snapshot` row so wiring a loader later is additive, not a schema change. Judgment: reasonable given no loader exists anywhere in the merged codebase; flagging only so a future item (loader) is tracked, not blocking this one. | None for this branch; ensure the settings-loader item (whichever CQ owns it) updates `create_scenario`/`create_default_scenarios`/`auto_price`'s `ConfigSnapshot()` calls, not just adds the loader. |
| 3 | minor | `backend/app/features/pricing/enrichment/service.py:151-158` (`_enrich_hoa`) | HOA is unconditionally `$0.00`/`FieldSource.DEFAULT` for every property, since no adapter/table models a real HOA source yet (catalog: Redfin/Zillow/listing). Correctly logged as Decision 5 and in "Deviations". A silent $0 HOA will understate `total_monthly_payment`/DSCR for any property that actually carries HOA dues (common on condos/townhomes) until a real source lands — worth a product callout, not a code defect. | None for this branch; when an HOA source lands, this handler is the single place to change. |
| 4 | minor | `docs/backlog/CQ-013-pricing-service/plan.md` Decision 11 / `post-dev.md` "New contracts" | `draft_default_quote_set` computes no recommendation, just wraps the `PricingResult`'s quote ids into `QuoteSetResult(quote_ids)`. Checked against CQ-011's own spec.md (§ Contracts table): it pins this exact shape — `application_id, PricingResult → QuoteSetResult(quote_ids)`, no recommendation field — so this isn't a scope-cutting deviation, it matches the consuming item's contract precisely. Noting only because system-design's "Draft quote set + recommendation" phrase reads as if this item should pick one; recommendation selection is explicitly CQ-019/22's job per this item's own decision log. | None; confirm CQ-019/22's spec still expects to own `quote_packages.recommended_quote_id` selection (it does, per this item's contracts note). |
| 5 | nit | `backend/app/features/pricing/scenarios/deps.py`, `backend/conftest.py:52` | `DEV_LO_ID` gets a hardcoded test default (`00000000-0000-0000-0000-000000000001`) via `os.environ.setdefault` in `backend/conftest.py`, which only loads under pytest — confirmed this file is never imported by `app.main`/production code, so this does not weaken non-test auth; `deps.get_current_lo_stub()` still 401s in any real environment where `DEV_LO_ID` is genuinely unset (`test_auth_stub.py` exercises exactly this via `get_settings` monkeypatch, not by unsetting the env var). No action needed. | None. |
| 6 | nit | `backend/app/integrations/conftest.py` (deleted) → `backend/conftest.py:102-121` | Moving `_fake_valkey`/`_clean_integration_calls` to the repo-wide autouse `backend/conftest.py` (Decision 2) is a reasonable simplification now that `pricing`/`quotes` tests also exercise mock adapters through `failure_toggle`; every other feature's tests get the same isolation for free with no behavior change (confirmed no other file still imports the deleted `app/integrations/conftest.py`). No action needed. | None. |

### Money/scale conversion audit (per review brief)

Grepped every non-test use of `note_rate` in `backend/app/features/pricing/` and `backend/app/features/quotes/`. The single conversion point is `dscr_loop.inputs_with_priced_product` (`product.note_rate / Decimal("100")`), used by every caller that turns a `PricedProductDTO` into `ScenarioInputs` for `compute_quote` (`create_scenario`, `autoquote_scenario`, `create_manual_quote`, `_price_group`, `_create_default_scenarios_investment`, `_create_default_scenarios_primary`, `run_two_pass_dscr` itself) — no other call site divides or otherwise touches the scale. `/quotes/preview` takes `ScenarioInputs` fields directly (already 0-1 fraction) and never touches a `PricedProductDTO`, so it correctly needs no conversion. `_persist_quote`'s `rate=product.note_rate` intentionally stores the percent-scale display value on the `Quote` row (matches `PricedProductRow.note_rate`'s own percent scale) and is never fed back into `compute_quote` unconverted. Golden re-verified end to end through the API (see Commands table above). No bug found.

### Other checks

- Decimal-only money: no `float(` in enrichment/scenarios/quotes-builder production code; all money/rate fields are `Decimal`.
- Primary-loan field suppression (rent/DSCR/cashflow/cost-seg/PPP): inherited correctly from CQ-008's `QuoteComputation` (investment-only fields `None` on `PRIMARY`); CQ-013 doesn't override or leak these — confirmed no primary-only code path re-populates them.
- `select_par_and_buydown`, default scenario sets (investment collapse rule, primary MI-removal step), and the DSCR two-pass loop's pass/flip/flag logic all read correctly against spec.md and are each backed by a test that exercises the actual branch (not just the happy path) — see `test_autoquote_selection.py`, `test_default_scenarios_investment.py`, `test_default_scenarios_primary.py`, `test_dscr_two_pass_loop.py`.
- `write_flag`/`resolve_flag` signatures used in `dscr_loop.py`/`enrichment/service.py` match `applications/verification/service.py`'s actual implementation exactly (Decision 3 confirmed correct, not just asserted).
- AC4's persona-7 test uses "missing RepresentativeFICO" rather than literally "missing Occupancy" (Occupancy is non-nullable in this schema) — spec.md explicitly allows "and equivalent for other fields" for this reason; not a finding.
