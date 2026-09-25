# CQ-010 — Implementation plan

## Decisions & questions (stage 1)

| # | Type | Item | Resolution |
| --- | --- | --- | --- |
| 1 | Decision | Phase split | Orchestrator directive: Phase A builds every piece that does not need CQ-013 (pricing/enrichment), calling CQ-013's pinned function names behind a clearly-marked seam (`seed/pricing_seam.py`). Phase B (after CQ-013 merges into `phase-p0-p1`) finishes wiring and drives personas 7/9/10 to their final table status. CQ-013 is not merged as of this session — this plan and post-dev.md cover Phase A only. |
| 2 | Decision | `import_from_los` scope | Per the orchestrator's ownership line ("LOS mock → application_parties, housing_history, employment, liabilities, assets"), `import_from_los(application_id, db)` only writes those 5 tables and flips `intake → verifying`. It does **not** create the `applications`/`properties` rows or set `occupancy`/`strategy`/`purchase_price` — those are known at intake time (LO-entered) and are written directly by `seed/loader.py` when it creates the `Application`/`Property` rows, before calling `import_from_los`. This matches CQ-011's activity table (`import_application` input is just `application_id`). |
| 3 | Decision | `applications.los_loan_guid` | Stores the persona's "LOS loan #" (e.g. `LOS-1000001`) verbatim — it doubles as the lookup key `import_from_los` passes to `MockLosClient.get_loan_file(loan_number)`. No other identifier exists for this purpose in the merged schema. |
| 4 | Decision | `LoanFileDTO` extension | The catalog's §3 (credit/assets/liabilities) sources `total_monthly_liabilities`, `liabilities_breakdown`, `total_verified_assets` from Encompass ("Import Liabilities"), and O12 adds `employment` fields for primary loans — but CQ-009's merged `LoanFileDTO` (`backend/app/integrations/los/schemas.py`) has no fields for any of these, and `import_from_los`'s owned tables include `employment`/`liabilities`/`assets`. Decision: add three new **optional, additive** fields to `LoanFileDTO` (`employment`, `liabilities`, `assets`, each `list[...] = []`) with new small DTOs in the same module, rather than reading `provider_los_records.payload` directly (which would bypass the mock's latency/failure-toggle/audit-log path CQ-011's retry policy depends on). Nothing else reads `LoanFileDTO` yet, so this is a pure addition, not a behavior change. |
| 5 | Decision | `SEED_FAST_ADAPTERS` | `seed/reset.py` sets `INTEGRATION_LATENCY_ENABLED=false` in `os.environ` before any `get_settings()` call when `SEED_FAST_ADAPTERS=1` (default `1` in `reset.py`, overridable), reusing CQ-009's existing latency toggle instead of adding a second one to `simulate_latency` — same effect (`AGENTS.md` "small gaps: decide and log"). |
| 6 | Decision | New deps | Added to `pyproject.toml` main deps: `pyyaml` (persona/provider fixtures), `pillow` + `reportlab` (sample doc generation + watermark), `bcrypt` (staff password hashes). Dev-only: `pypdf` (test reads back the burned-in PDF watermark text). `pythonpath` gains `.` so `seed/tests` can `import seed`/`import app` when invoked directly. |
| 7 | Decision | MinIO bucket | `clearquote-demo-docs` (spec's bucket) isn't created by `infra/docker-compose.yml`'s `minio-init` (which only makes `clear-quote`) — `seed/generators/documents.py` creates it idempotently (`create_bucket`, ignore `BucketAlreadyOwnedByYou`) before uploading. |
| 8 | Decision | Background generator names | No `faker` dependency added (avoids a new heavyweight dep for one generator); names are built deterministically from small first/last-name pools indexed by the seeded `random.Random`. |

### Phase B decisions (CQ-013 merged `a95498b`/`85e0462`)

| # | Type | Item | Resolution |
| --- | --- | --- | --- |
| 9 | Decision | Pricing seam signatures | Phase A guessed `(application_id, db, ...)`; CQ-013's real functions all take `(db, application_id, ...)` first. `seed/pricing_seam.py` rewritten to call the real, merged functions directly -- no more try/except `ImportError` or `PRICING_AVAILABLE` flag. |
| 10 | Decision | `representative_fico` field_value | Nothing in the merged codebase (`enrich_pricing_fields`, CQ-011's 6 activities) writes `field_values.representative_fico`, but `auto_price`/`validate_ob_required_fields` both require it. Since this item already seeds `provider_credit_reports`, `seed_persona` pulls credit itself (`_seed_representative_fico`, a new step, not part of `pricing_seam.py`) and writes that one field -- an input, not a computed figure. Skipped for personas whose `missing_fields` includes `occupancy_type` (Aisha Coleman): CQ-013's own post-dev.md documents "missing RepresentativeFICO" as this schema's real equivalent of persona 7's "missing Occupancy" (Occupancy is non-nullable, so literally missing it is structurally impossible), so withholding her FICO pull reproduces the intended defect precisely, not a fabrication. |
| 11 | Decision | `Property.number_of_units` vs. the persona table's "Beds" column | CQ-013's `_enrich_market_rent_ltr`/`_enrich_str_revenue` look up `provider_rents`/`provider_str_revenue` by `(property.zip, property.number_of_units)`, not a bedroom count (the schema has no such column). All 10 personas are `single_family` (1 unit), so `seed/providers/rents.yaml` and `str_revenue.yaml` are keyed on `beds=1` for every market (not the persona table's "Beds" column, which stays a purely descriptive field). Phase A's original `beds=persona["beds"] or 1` keying silently produced `RentDataNotFoundError`/`StrDataNotFoundError` once the real enrichment ran. |
| 12 | Decision | Marcus Hale's STR revenue | The generic `price * 0.14` proxy every other market uses gave Marcus Hale (Tampa) a DSCR > 1, contradicting system-design.md's own persona description ("DSCR < 1 ... negative cashflow shown honestly"). `seed/providers/str_revenue.yaml`'s Tampa (33602) row is pinned to `$24,000` annual revenue instead, computed against the engine's actual PITIA at that scenario's rate/loan (~$2,080-$2,210/mo) so DSCR stays below 1 at every priced rate. Verified against the real seeded quote: DSCR 0.82, monthly cashflow -$360.53, and `year_one_tax_savings` = $24,275.78 -- matching data-field-catalog override O4's pinned golden value ("$75,862 / $24,276 for $342,000") exactly. |
| 13 | Decision | `DEV_LO_ID` | `seed/users.yaml`'s Jordan Lee (first LO) is pinned to `id: 00000000-0000-0000-0000-000000000001`, matching `backend/conftest.py`'s and `.env.example`'s `DEV_LO_ID` default, so a developer hitting the pricing routes locally against a freshly-`demo-reset` database has a real `users` row behind the stub-auth id out of the box. `seed_users` now honors an optional `id` field in the YAML fixture. |

## Why

`make demo-reset` needs to give every later item (and every other in-flight worktree) a realistic, deterministic database. This item is pure data plumbing: no new product logic, just fixtures, generators, and calls into already-owned or self-owned service functions.

## What changes (Phase A)

| Area | Files |
| --- | --- |
| LOS DTO extension | `backend/app/integrations/los/schemas.py` (additive) |
| Owned service | `backend/app/features/applications/service.py` (new — `import_from_los`) |
| Seed package | `seed/__init__.py`, `seed/config.py`, `seed/personas/*.yaml` (10), `seed/providers/*.yaml` (5), `seed/users.yaml`, `seed/loader.py`, `seed/reset.py`, `seed/pricing_seam.py`, `seed/generators/background_applications.py`, `seed/generators/documents.py` |
| Tests | `seed/tests/conftest.py`, `seed/tests/test_persona_statuses.py`, `seed/tests/test_provider_rows_seeded.py`, `seed/tests/test_users_seeded.py`, `seed/tests/test_background_generator_determinism.py`, `seed/tests/test_documents_watermarked.py`, `seed/tests/test_personas_match_engine.py` |
| Build config | `pyproject.toml` (deps, pythonpath), `Makefile` (`demo-reset` body, `test` gains `seed`) |

## Tasks

| Task | Description | Depends on | Owned files | Test(s) |
| --- | --- | --- | --- | --- |
| T1 | Extend `LoanFileDTO`; write `import_from_los` | — | `los/schemas.py`, `applications/service.py` | `backend/app/features/applications/tests/test_service.py` |
| T2 | Persona YAML fixtures (10) + provider YAML fixtures (5 tables x 10 markets) + users YAML | — | `seed/personas/*`, `seed/providers/*`, `seed/users.yaml` | covered by loader tests |
| T3 | `seed/loader.py`: create client/application/property/provider rows, run import+verify, write `activity_events`, D2 fixture rows for personas 9/10 (data authored now, wired to real quotes in Phase B) | T1, T2 | `seed/loader.py` | `seed/tests/test_persona_statuses.py`, `test_provider_rows_seeded.py`, `test_users_seeded.py` |
| T4 | `seed/pricing_seam.py`: seam importing CQ-013's pinned names, `PRICING_AVAILABLE` flag, no-op cleanly when absent | — | `seed/pricing_seam.py` | exercised via T3 tests (seam-absent branch) |
| T5 | Background generator (~200 apps, `random.Random(SEED_RNG_SEED)`) | T2 | `seed/generators/background_applications.py` | `seed/tests/test_background_generator_determinism.py` |
| T6 | Sample doc generator (PDF+PNG, SAMPLE watermark, MinIO upload) | — | `seed/generators/documents.py` | `seed/tests/test_documents_watermarked.py` |
| T7 | `seed/reset.py` entrypoint + Makefile wiring, timing | T3, T5, T6 | `seed/reset.py`, `Makefile` | manual `time make demo-reset` |
| T8 | Golden-value test proving persona figures equal `quote_engine` output for whatever stage Phase A reaches (full AC1/AC8 land in Phase B once pricing runs) | T3 | `seed/tests/test_personas_match_engine.py` | itself |

## Wave schedule

| Wave | Tasks | Why |
| --- | --- | --- |
| 1 | T1, T2, T4, T6 | No interdependencies |
| 2 | T3 | Needs T1/T2/T4 |
| 3 | T5, T8 | Needs T2/T3 |
| 4 | T7 | Needs everything |

## Acceptance → test map (Phase A status)

| Criterion | Test | Phase A result |
| --- | --- | --- |
| AC1 | `seed/tests/test_personas_match_engine.py` | Partial: proves no hand-typed numbers in what Phase A produces; full "priced" trace needs CQ-013 (Phase B) |
| AC2 | `seed/tests/test_persona_statuses.py::test_persona_final_statuses_match_table` | Partial: persona 8 (`needs_attention`) fully matches; personas reaching `priced`/`sent`/`option_selected` land in Phase B |
| AC3 | `seed/tests/test_provider_rows_seeded.py` | Full |
| AC4 | `seed/tests/test_users_seeded.py` | Full |
| AC5 | `seed/tests/test_background_generator_determinism.py` | Full |
| AC6 | `seed/tests/test_documents_watermarked.py` | Full |
| AC7 | `seed/tests/test_persona_statuses.py::test_grace_and_luis_downstream_rows` | Phase B (needs a priced quote to reference) |
| AC8 | `seed/tests/test_personas_match_engine.py::test_no_reference_sheet_errors_reproduced` | Full for engine-level values already computable without pricing wiring |

## Progress

- [x] T1
- [x] T2
- [x] T3
- [x] T4
- [x] T5
- [x] T6
- [x] T7
- [x] T8

### Review round 1 fixes (orchestrator decisions, post-dev.md findings #1/#2/#3)

| # | Type | Item | Resolution |
| --- | --- | --- | --- |
| 14 | Decision | `applications.occupancy` nullable | New migration `e7b20ff388a7` (does not edit `initial_schema`). `Application.occupancy: Occupancy \| None`; `VerificationContext.occupancy` (CQ-012's schema) also widened to `Occupancy \| None` -- it was assigned `application.occupancy` directly and would otherwise fail pydantic validation the moment any application has a `NULL` occupancy. `alembic check`/upgrade/downgrade/upgrade all verified clean. No OpenAPI-exposed schema references `occupancy` (`export_openapi.py` re-run, byte-identical output) -- no `packages/api-client` regen needed. |
| 15 | Decision | `import_from_los` copies occupancy from the LOS record | Reverses this item's original decision #2. `seed/loader.py` no longer sets `Application.occupancy` at creation (`None`, matching real intake); `import_from_los` maps `LoanFileDTO.occupancy_type` ("Investment_Property"/"Primary_Residence") onto the enum, defaulting to `None` for anything else/missing (Aisha Coleman's exact LOS defect). `strategy` is untouched -- already nullable, no persona has a "missing investment_strategy" defect, still LO-entered at intake. |
| 16 | Decision (minimal edit, CQ-013-owned files) | `Occupancy` OB field / flag field_key | `pricing/scenarios/ob_request.py::build_ob_search_request` previously defaulted the OB `Occupancy` field to `"PrimaryResidence"` whenever `application.occupancy` wasn't literally `INVESTMENT` -- meaning it could never actually be missing. Now it's `None` when `application.occupancy is None`, so `MockPricingClient._missing_fields` correctly flags it. `pricing/enrichment/service.py::validate_ob_required_fields` maps the OB field name `"Occupancy"` to `flags.field_key = "occupancy_type"` when writing/resolving (`_flag_field_key`) -- the one exception; every other missing field (e.g. `RepresentativeFICO`) keeps its OB wire name, matching CQ-013's own `test_ob_validation.py`. Pinned by two new tests in `backend/app/features/pricing/enrichment/tests/test_occupancy_validation.py` (exact message/field_key, and resolve-once-fixed). |
| 17 | Decision | Soft credit pull moves into `import_from_los` | `_seed_representative_fico` deleted from `seed/loader.py`. `import_from_los` now runs a real `MockCreditClient.pull_credit(loan_number, CreditPullType.SOFT_PULL)` and writes `field_values.representative_fico` from `experian_score` (catalog: soft pull populates Experian only) -- an owned pipeline step now, not a seed-only shortcut, so CQ-011's real (non-seed) pipeline gets a FICO too. `ImportResult` gained `occupancy`/`representative_fico` fields. Raises `CreditPullFailedError` (propagates, same as `LoanNotFoundError`) if no seeded `provider_credit_reports` row matches -- covered by a new test. |
| 18 | Decision | No plaintext staff password anywhere | `seed/users.yaml`'s `password` field removed entirely. `seed/loader.py::seed_users` reads the shared demo password via `get_settings().seed_staff_password` (new `Settings` field, `.env`'s `SEED_STAFF_PASSWORD`, empty by default in `.env.example`) and bcrypt-hashes it once. `seed/reset.py::main()` fails fast (`SystemExit(1)`, clear message, before touching the DB) if unset. Grepped the whole tree (docs included) for the old literal -- clean. |

Minor findings #4 (CQ-013's `number_of_units`-as-`beds` keying) and #5 (CI doesn't run `pytest seed`) are left as-is per the orchestrator's call — recorded as follow-ups in `handoff.md` (the orchestrator owns #5 in the CI pass).
