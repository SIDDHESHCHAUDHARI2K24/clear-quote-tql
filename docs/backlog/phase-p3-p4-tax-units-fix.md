# P3/P4 fix unit: property-tax seed rates stored as fractions, read as percents

Small fix unit, approved by the human 2026-09-25 ("Fix seed now, small unit"). Branch
`p34-tax-units-fix` off `origin/phase-p3-p4`, PR into `phase-p3-p4`.

## Bug

`seed/providers/tax_rates.yaml` stores each county's `annual_rate_pct` as a
fraction (e.g. Hillsborough `"0.0089"`) instead of a percent. The field name
and every consumer (`ProviderTaxRate.annual_rate_pct`, `TaxRateDTO.annual_rate_pct`,
and `seed/providers/insurance_factors.yaml`'s own `"0.50"` for 0.50%) treat it
as percent-scale: `backend/app/features/pricing/enrichment/service.py::_enrich_tax`
divides it by 100, once, at the enrichment boundary, to produce the 0-1
fraction `property_tax_annual_rate` the engine consumes
(`docs/design/data-field-catalog.md` "third-party data enrichment fields":
percent examples like Buncombe 0.601%, Hillsborough 1.15%).

With the yaml storing `0.0089` as if it were already a percent, `_enrich_tax`
produced `0.0089 / 100 = 0.000089` -- a fraction 100x too small. Every seeded
persona's property tax landed at roughly 1/100th of a realistic county rate
(Marcus Hale: ~$2.54/mo instead of ~$254/mo on a $342,000 Hillsborough FL
property).

The code path (percent -> `/100` -> fraction) was correct; only the seed data
was wrong.

## Fix

Multiplied every `annual_rate_pct` row in `seed/providers/tax_rates.yaml` by
100 so the field is percent-scale, matching `insurance_factors.yaml`'s
existing convention and the data-field-catalog's percent examples:

| County, state | Before (wrong) | After (percent) |
| --- | --- | --- |
| Hillsborough, FL | 0.0089 | 0.89 |
| Polk, FL | 0.0089 | 0.89 |
| Hamilton, IN | 0.0085 | 0.85 |
| Marion, IN | 0.0085 | 0.85 |
| Allen, IN | 0.0085 | 0.85 |
| Buncombe, NC | 0.0064 | 0.64 |
| Cuyahoga, OH | 0.0153 | 1.53 |
| Franklin, OH | 0.0153 | 1.53 |
| Denver, CO | 0.0051 | 0.51 |
| Maricopa, AZ | 0.0062 | 0.62 |

No code change: `_enrich_tax`'s `/100` conversion, `ProviderTaxRate.annual_rate_pct`
(`Numeric(6, 4)`, holds up to 99.9999 -- these new values fit comfortably),
and every downstream consumer (`quote_engine.monthly_tax_amount`, matches
service, report builder) were already correct for percent-scale input.

Everywhere else in the codebase that referenced a `property_tax_annual_rate`
*fraction* directly (test fixtures, `backend/scripts/build_report_fixtures.py`,
`seed/tests/test_personas_match_engine.py`'s hand-typed `ScenarioInputs`) had
already used the *correct* final fraction (e.g. `Decimal("0.0089")` = 0.89%)
independent of the buggy yaml, so none of those needed changes. Test fixtures
that build a `ProviderTaxRate` directly with a percent-scale `annual_rate_pct`
(e.g. `Decimal("0.6010")` for Buncombe's 0.601%) were also already correct.

## Numbers before/after

**Marcus Hale** (STR, $342,000, Hillsborough FL, Par option):

| | Before (buggy) | After (fixed) |
| --- | --- | --- |
| Monthly property tax | $2.54 | $253.65 |
| Total monthly payment | $1,960.53 | $2,211.64 |
| DSCR ratio | 0.82 | 0.72 |
| DSCR bucket | BELOW_1_00 | BELOW_1_00 (unchanged) |

**Priya Nair** (primary, $420,000, Hamilton IN, Par option):

| | Before (buggy) | After (fixed) |
| --- | --- | --- |
| Monthly property tax | $2.98 | $297.50 |
| Total monthly payment | $2,301.73 | $2,596.25 |

(Priya is a primary-occupancy scenario -- no DSCR bucket applies; primary
loans never show DSCR per AGENTS.md.)

"Before" figures above are derived arithmetically (tax is additive in
`total_monthly_payment`, independent of P&I/insurance/HOA/MI, so subtracting
the after-fix tax and adding the pre-fix tax back in is exact) rather than by
reverting the yaml and re-seeding, to avoid a second full pipeline run.

## Persona outcome check (no silent changes)

All 10 personas' `seed_end_status` (from `seed/personas/*.yaml`) still match
after `make demo-reset`:

```
marcus_hale: priced          kathleen_mcreynolds: priced
priya_nair: priced           daniel_ortiz: priced
sam_reed: priced              tom_lisa_brandt: priced
aisha_coleman: needs_attention  ben_ford: needs_attention
grace_kim: sent               luis_romero: option_selected
```

**DSCR bucket, all 7 investment personas** (Par option, arithmetic before/after
per the method above; `dscr_bucket` recomputed with the same
`bucket_for_dscr` thresholds the engine uses: <1.00, <1.25, >=1.25):

| Persona | County | DSCR before | DSCR after | Bucket before | Bucket after |
| --- | --- | --- | --- | --- | --- |
| Marcus Hale | Hillsborough FL | 0.82 | 0.72 | BELOW_1_00 | BELOW_1_00 |
| Kathleen McReynolds | Polk FL | 1.32 | 1.17 | GE_1_25 | **ONE_TO_1_25** |
| Sam Reed | Buncombe NC | 1.69 | 1.54 | GE_1_25 | GE_1_25 |
| Tom & Lisa Brandt | Cuyahoga OH | 1.32 | 1.08 | GE_1_25 | **ONE_TO_1_25** |
| Aisha Coleman | Franklin OH | n/a -- blocked before pricing (missing fields), tax value never reaches DSCR | | | |
| Grace Kim | Denver CO | 1.32 | 1.23 | GE_1_25 | **ONE_TO_1_25** |
| Luis Romero | Maricopa AZ | 1.63 | 1.50 | GE_1_25 | GE_1_25 |

Three personas' DSCR bucket does move, from `GE_1_25` to `ONE_TO_1_25`:
Kathleen McReynolds, Tom & Lisa Brandt, and Grace Kim. This is a real,
expected consequence of the fix (their old, 100x-too-small tax made their
DSCR look better than it really is), not an artifact of the fix being wrong.
Checked each against its documented intended demo point
(`docs/design/system-design.md` "Seed data personas" table, lines 326-334)
before concluding this isn't a big gap:

- **Marcus Hale** -- "DSCR < 1" is the explicit point; still `BELOW_1_00`. Unaffected.
- **Kathleen McReynolds** -- "Property matches; TBD letter; par vs buydown", no DSCR
  number named. `_create_default_scenarios_investment` (`backend/app/features/
  pricing/scenarios/service.py:430-536`) collapses her two DSCR pricing groups
  into one when the actual bucket matches the assumed `ONE_TO_1_25` bucket
  (line 481: `if actual_bucket == DSCRBucket.ONE_TO_1_25`) -- true for her now,
  false before. Both Par and Buydown quotes still exist in the single
  collapsed group (lines 467-479), so "par vs buydown" is still demonstrable;
  what changes is one group instead of two, with a "same pricing tier as the
  1.00 assumption" note. No current test (backend or seed) asserts her group
  count, so nothing breaks today -- flagging this for CQ-018 (quote builder,
  not yet built) to be aware of when it renders scenario groups from real
  seed data. Verified directly against the seeded `scenarios` table after
  `make demo-reset`: Kathleen, Tom & Lisa Brandt and Grace Kim each now have
  exactly one `scenarios` row (`dscr_bucket=ONE_TO_1_25`, collapsed), where
  Sam Reed and Luis Romero (bucket unchanged) each still have two.
- **Sam Reed** -- "high STR revenue, DSCR > 1.25 bucket" is the explicit,
  numeric point. After the fix: DSCR 1.54, bucket `GE_1_25` -- still holds.
- **Tom & Lisa Brandt** -- "Co-borrower tab; combined credit", no DSCR number
  named. Unaffected by the bucket move.
- **Aisha Coleman** -- needs_attention from a missing required field
  (`validate_ob_required_fields`), raised before enrichment's tax value ever
  reaches a DSCR computation. Unaffected by this fix.
- **Grace Kim** -- "Stale banner; forced re-price", no DSCR number named.
  Unaffected by the bucket move.
- **Luis Romero** -- no DSCR number named; bucket unchanged anyway (`GE_1_25`).

No persona's documented intended demo point breaks, and no persona's
`seed_end_status` changed (verified below). CQ-023's Kathleen McReynolds
match-count test (`test_matches_kathleen`, exactly 3 in band) still passes --
ranking inputs shifted with the higher tax, but the count didn't.

This is not a big gap: nothing documented breaks, and the DSCR/bucket moves
are the fix working as intended (realistic tax lowers realistic DSCR). Not
stopping for human input, but recording it here per AGENTS.md ("do not
silently change persona expectations") so a later CQ-018 worker building
Kathleen's scenario-group UI from real seed data isn't surprised to find one
collapsed group instead of two.

## Files changed

- `seed/providers/tax_rates.yaml` -- the fix: 10 rows, `annual_rate_pct` x100
- `seed/tests/test_tax_rate_units.py` -- new: (1) every yaml row's percent is
  in a sane range (0.1%-4%), (2) a seeded persona's `property_tax_annual_rate`
  field value, as a fraction, is realistic (0.001-0.04)
- `docs/backlog/phase-p3-p4-tax-units-fix.md` -- this file

`packages/ui/src/report/__fixtures__/*.json` (CQ-021 fixtures) were
regenerated via `uv run python backend/scripts/build_report_fixtures.py` and
came out byte-identical -- that script's `ScenarioInputs.property_tax_annual_rate`
values were already hand-derived correct fractions, not read from the yaml.
`apps/lo-console/src/features/pricing/__fixtures__/` (CQ-017) doesn't exist on
this base branch (CQ-017 isn't merged into `phase-p3-p4` yet).

## Test log

Environment: `scripts/worktree-env.sh 11` (slot 11: `cq_dev_s11`/`cq_test_s11`,
API port 8111), against the already-running shared infra.

- `uv run pytest seed/tests/test_tax_rate_units.py -v` -- red before the data
  fix (both new tests failed on the buggy yaml/seeded fraction), green after.
- `uv run pytest backend -q` -- 444 passed
- `uv run pytest seed -q` -- 30 passed (includes `test_persona_statuses.py`,
  `test_personas_match_engine.py`, `test_provider_rows_seeded.py`)
- `pnpm -r run test` -- all workspaces green (packages/api-client,
  packages/ui incl. report component/gallery tests, apps/lo-console,
  apps/borrower-portal)
- `make lint` -- ruff check/format, mypy (`backend/app`, `conftest.py`,
  `tests`, `scripts`), eslint, tsc, prettier -- all clean
- `make demo-reset` -- 1.2s (well under the 60s budget); all 10 personas'
  final statuses match `seed_end_status`
- Manual verification: `property_tax_annual_rate` field values for Marcus
  Hale (`0.0089`) and Priya Nair (`0.0085`) are realistic 0-1 fractions
