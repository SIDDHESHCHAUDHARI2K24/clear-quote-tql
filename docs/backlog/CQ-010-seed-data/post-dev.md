# CQ-010 — Post-development notes (Phase A)

## Summary

Phase A only (orchestrator directive): CQ-013 (pricing/enrichment) has not
merged into `phase-p0-p1` as of this session, so the pricing/quote stages
are behind a clearly-marked seam (`seed/pricing_seam.py`) that no-ops until
CQ-013 lands. Everything else the spec scopes to CQ-010 is built and
tested: the `seed/` package (10 persona YAML fixtures with full LOS 1003
payloads, 5+2 `provider_*` fixture YAMLs, staff users), `applications.
service.import_from_los` (this item's owned service function, wrapping
`MockLosClient` and writing `application_parties`/`housing_history`/
`employment`/`liabilities`/`assets`), a deterministic ~200-app background
generator, watermarked sample-document generation + MinIO upload, and
`make demo-reset` (drop/recreate `cq_dev`'s public schema, migrate, seed,
print a timed summary). `time make demo-reset` runs in ~2s.

## Deviations from spec

| Spec said | Built | Why |
| --- | --- | --- |
| Personas reach `priced`/`sent`/`option_selected` per the table | Personas without a defect stop at `ready_to_price`; Ben Ford still reaches `needs_attention` | CQ-013's `enrich_pricing_fields`/`validate_ob_required_fields`/`auto_price`/`draft_default_quote_set` aren't merged; `seed/pricing_seam.py` calls them by their pinned names and no-ops (`PRICING_AVAILABLE=False`) rather than reimplementing pricing logic (out of scope, would duplicate CQ-013). This is Decision D1's Phase A/B split, directed by the orchestrator. |
| Aisha Coleman ends `needs_attention` ("Cannot price: missing Occupancy") | Ends `ready_to_price` in Phase A | That exact flag is raised by CQ-013's OB-required-field validation (`write_flag` call already anticipated in CQ-012's own tests), not a CQ-012 verification rule -- confirmed by reading `verification/service.py`'s docstring and `verification/tests/test_service.py::test_write_flag_upserts`. |
| Grace Kim / Luis Romero: `sent` / `option_selected` fixture layer (Decision D2) | Fixture-layer mechanism (`seed.loader.apply_send_fixture`) is implemented and ready, but not invoked -- there is no priced `Quote` row yet to reference | Same CQ-013 dependency; `test_persona_statuses.py::test_grace_and_luis_downstream_rows` is `pytest.skip`ped when `PRICING_AVAILABLE` is False, and will run for real, unmodified, once CQ-013 merges (the test reads `seed.pricing_seam.PRICING_AVAILABLE` itself). |
| `LoanFileDTO` (CQ-009) had no employment/liabilities/assets/co_borrower_dob fields | Added as optional, additive fields | `import_from_los`'s owned scope (application_parties/housing_history/employment/liabilities/assets) needs a source for the latter three, and CQ-012's `dob_format` rule already checks a co-borrower's DOB; catalog §3/O12 source these from Encompass too. Nothing else read `LoanFileDTO` yet, so purely additive. See plan.md decision #4. |

## Acceptance evidence (stage 7) — Phase A

| Criterion | Status | Evidence |
| --- | --- | --- |
| AC1 | Partial | `time make demo-reset` → 1.5-2.0s (well under 60s). `seed/tests/test_personas_match_engine.py` (3 tests) proves the reference-sheet corrections and reproduces Marcus Hale's raw seed inputs through `quote_engine.compute_quote` directly. Full "every persona traces to a priced `quote_engine` output" needs CQ-013 (Phase B). |
| AC2 | Partial | `pytest seed/tests/test_persona_statuses.py::test_persona_final_statuses_match_table` passes: Ben Ford → `needs_attention` (full spec match); the other 9 → `ready_to_price` in Phase A (test is `PRICING_AVAILABLE`-aware and will assert the full `seed_end_status` table once CQ-013 merges, no test-file edit needed). |
| AC3 | **Full** | `pytest seed/tests/test_provider_rows_seeded.py` (8 tests) — all 5 named `provider_*` tables have ≥1 row per persona market; LOS/Tax/Rent/Str/Credit/Insurance/CRM adapters return non-empty for every applicable persona; PropertySearch for all 7 investment personas. (OB/Pricing adapter intentionally out of scope here — see test file docstring; building a valid `PricingRequestDTO` is CQ-013's `build_ob_search_request` logic.) |
| AC4 | **Full** | `pytest seed/tests/test_users_seeded.py` (2 tests) — exactly 2 LO/1 Manager/1 Admin, real bcrypt hashes (`$2b$` prefix, `bcrypt.checkpw` round-trips). |
| AC5 | **Full** | `pytest seed/tests/test_background_generator_determinism.py` (3 tests) — 190-210 rows, identical `by_status`/`by_lo` across two runs with the same `SEED_RNG_SEED`, and a different seed can move the distribution. Also confirmed at the `make demo-reset` level: two consecutive runs produced the identical background breakdown `{'intake': 28, 'verifying': 27, 'needs_attention': 24, 'ready_to_price': 31, 'stale': 12, 'priced': 53, 'sent': 25}` and `100`/`100` per LO. |
| AC6 | **Full** | `pytest seed/tests/test_documents_watermarked.py` (4 tests) — every persona gets ≥1 `documents` row; object keys end `-SAMPLE.pdf`/`-SAMPLE.png`; PDF watermark text extracted via `pypdf`; PNG watermark pixel-verified at a deterministic coordinate; round-tripped through the real MinIO container (`clearquote-demo-docs` bucket, created on demand). |
| AC7 | Deferred to Phase B | No priced quote exists yet for the D2 fixture layer to attach to; `apply_send_fixture` is implemented and `test_grace_and_luis_downstream_rows` is written to run unmodified once CQ-013 merges (currently `pytest.skip`ped with a clear reason). |
| AC8 | **Full** for what's engine-computable now | `pytest seed/tests/test_personas_match_engine.py::test_no_reference_sheet_errors_reproduced` — reproduces the $2,394 title fee on $342,000 (not the catalog's flawed $2,100), proves cash-to-close includes discount points (not excludes them, unlike the flawed reference report), and that `ScenarioInputs` structurally rejects mixed LTR/STR inputs. |

## Test log (stage 5)

| Check | Command | Result |
| --- | --- | --- |
| Backend + seed tests | `uv run pytest backend seed` | 190 passed, 1 skipped |
| Lint | `uv run ruff check backend seed` | All checks passed |
| Format | `uv run ruff format --check backend seed` | All formatted |
| Types (backend, `make lint`'s scope) | `uv run mypy backend/app backend/conftest.py backend/tests backend/scripts` | Success: no issues found in 177 source files |
| Types (seed, extra self-check — not in `make lint`'s scope) | `MYPYPATH=backend uv run mypy seed --ignore-missing-imports` | Success: no issues found in 16 source files |
| Demo reset timing | `time make demo-reset` | `elapsed: 1.5s` (well under the 60s budget), run twice with identical background counts |

Frontend (`pnpm -r run test`/lint/tsc) not run — this item touches no frontend code.

## Review findings (stage 6)

(left for the fresh reviewer)

## How to test manually

1. `make up` (if the shared stack is down).
2. `make demo-reset` — prints a summary; note it says pricing is skipped
   until CQ-013 merges.
3. `uv run pytest backend seed -q`.

## Follow-ups (Phase B, once CQ-013 merges into `phase-p0-p1`)

- `git merge phase-p0-p1` into this branch (or re-verify after a rebase), no
  code changes expected in `seed/pricing_seam.py` beyond confirming the
  guessed `draft_default_quote_set(application_id, pricing_result, db)`
  call signature matches CQ-013's real one (log a `Decision:` if it moved).
- Re-run `pytest seed -q`: `test_persona_final_statuses_match_table` and
  `test_grace_and_luis_downstream_rows` will exercise the full table/D2
  fixture layer automatically (both already read
  `seed.pricing_seam.PRICING_AVAILABLE`).
- Re-run `time make demo-reset` and confirm it's still under 60s with the
  pricing stage now actually running for all 10 personas.
- Update this file's AC1/AC2/AC7/AC8 rows from "Partial"/"Deferred" to
  "Full" with the new evidence.
