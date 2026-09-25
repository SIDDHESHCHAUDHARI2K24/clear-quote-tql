# CQ-010 Seed data & demo reset

| Field | Value |
| --- | --- |
| Phase | P1 Data, engine, pipeline |
| Depends on | CQ-008, CQ-009 |
| Kaneo task | CQ-010 in Kaneo (task id `sn7qq7525r4ww2tmdpe3htp3`) |
| Branch | `cq-010-seed-data` |
| Status | Ready — filled from design docs on 2026-09-24 |

## Goal

Running `make demo-reset` gives every later item a live database in under 60 seconds: 10 hand-designed personas at their correct pipeline status, ~200 background applications so lists and the dashboard look real, and sample documents in MinIO — every number produced by `quote_engine`, none typed in.

## Scope

1. `seed/` package: persona fixtures (YAML), a deterministic background-application generator, provider fixture rows, staff users, sample documents, and the `demo-reset` entrypoint.
2. The 10 personas from `system-design.md` §"Seed data personas", each with a full raw-input record (see table below) plus its seeded LOS record.
3. `provider_*` fixture rows (tax rate, rent, STR revenue, OB rate sheet, listings) for each of the 10 persona markets, read by CQ-009's mock adapters.
4. A fixed-seed generator producing ~200 background applications spread across statuses, LOs, occupancy/strategy and the same 10 markets.
5. Sample documents (PDF/PNG) watermarked "SAMPLE", uploaded to MinIO and linked from `documents` rows.
6. Staff users: 2 LO, 1 Manager, 1 Admin (login only becomes usable in CQ-014; this item only inserts the rows and bcrypt hashes).
7. `make demo-reset`: drop/recreate schema, migrate, seed everything above, print a summary — under 60 s.
8. A test proving every persona-attached dollar/rate figure equals `quote_engine` output computed from the seeded raw inputs (no number is hand-typed anywhere in `seed/`).

## Out of scope

- The Temporal workflow itself and its activities, retry policy and resume signal (CQ-011). This item drives personas to their pipeline status by calling the same stage service functions CQ-011 later wraps as activities — see Decision D1.
- Verification rule logic (CQ-012) and pricing/enrichment calculation logic (CQ-013) — this item only supplies inputs and calls their service entry points.
- Mock adapter implementations and `provider_*` table schemas (CQ-009) — this item only inserts fixture rows into tables CQ-009 defines.
- `applications` / `field_values` / `flags` / `quote_packages` / `activity_events` table schemas and the `application_status` enum (CQ-007) — this item only writes rows.
- Staff login, OTP, sessions (CQ-014).
- The stale-quote scheduled job that flips sent/priced to stale after 21 days (CQ-030) — Grace Kim's quote is seeded as `sent` 25 days ago and stays that way until CQ-030 ships and runs.
- LO/borrower UI for resolving flags, sending quotes or selecting an option (CQ-019, CQ-020, CQ-024, CQ-028, CQ-032) — for Grace and Luis this item writes the downstream `sent`/`option_selected` rows directly as fixtures (Decision D2), it does not exercise those features.

## References

- `docs/design/system-design.md` — "Seed data personas", "Application status machine", "Data model", "Emulated integrations", "Calculation engine" (golden test values reused for Marcus Hale), repo layout (`seed/`).
- `docs/design/data-field-catalog.md` — §1 borrower/co-borrower fields, §2 housing history, §4 property/geography (`subject_zip`, `subject_county`), overrides O2 (occupancy enum), O7/O8 ("seed numbers come from the quote engine", correct title figure).
- `AGENTS.md` — project map (`seed/`), Make targets table, money-math rule (quote_engine only).

## Persona table (raw inputs the seed loads; every derived $/% figure comes from `quote_engine` + the mock adapters at seed time)

| # | Persona | Email | Occupancy/Strategy | Market (city, state, zip, county) | Price | Down % | PPP | FICO | Beds | LOS loan # | Vesting | Co-borrower | Housing (current, mo) | LOS defect | Pipeline end status | Seed end status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | Marcus Hale | marcus.hale@clearquote-demo.test | Investment / STR | Tampa, FL, 33602, Hillsborough | $342,000 | 20% | 5y | 760 | 3 | LOS-1000001 | Personal Name | none | 60 | — | priced | priced |
| 2 | Kathleen McReynolds | kathleen.mcreynolds@clearquote-demo.test | Investment / LTR | TBD; buy-box Davenport, FL, 33896, Polk | $300,000 | 25% | 5y | 720 | 4 | LOS-1000002 | Personal Name | none | 48 | — | priced | priced |
| 3 | Priya Nair | priya.nair@clearquote-demo.test | Primary | Carmel, IN, 46032, Hamilton | $420,000 | 20% | none | 760 | n/a | LOS-1000003 | Personal Name | none | 48 | — | priced | priced |
| 4 | Daniel Ortiz | daniel.ortiz@clearquote-demo.test | Primary | Indianapolis, IN, 46201, Marion | $285,000 | 5% | none | 700 | n/a | LOS-1000004 | Personal Name | none | 36 | — | priced | priced |
| 5 | Sam Reed (Asheville Holdings LLC) | sam.reed@clearquote-demo.test | Investment / STR | Asheville, NC, 28803, Buncombe | $525,000 | 25% | 5y | 780 | 4 | LOS-1000005 | Title + Lien in LLC (`Asheville Holdings LLC`) | none | 24 | — | priced | priced |
| 6 | Tom & Lisa Brandt | tom.brandt@clearquote-demo.test | Investment / LTR | Cleveland, OH, 44102, Cuyahoga | $250,000 | 25% | 5y | 690 | 3 | LOS-1000006 | Personal Name | Lisa Brandt | 30 | — | priced | priced |
| 7 | Aisha Coleman | aisha.coleman@clearquote-demo.test | Investment / LTR | Columbus, OH, 43215, Franklin | $310,000 | 25% | 5y | 715 | 3 | LOS-1000007 | Personal Name | none | 40 | `occupancy_type` null in LOS record | needs_attention ("Cannot price: missing Occupancy") | needs_attention |
| 8 | Ben Ford | ben.ford@clearquote-demo.test | Primary | Fort Wayne, IN, 46802, Allen | $260,000 | 10% | none | 730 | n/a | LOS-1000008 | Personal Name | none | 14 (no prior address on file) | housing history 14 mo < 24 mo | needs_attention (housing-history flag) | needs_attention |
| 9 | Grace Kim | grace.kim@clearquote-demo.test | Investment / LTR | Denver, CO, 80202, Denver | $330,000 | 25% | 5y | 745 | 2 | LOS-1000009 | Personal Name | none | 60 | — | priced | **sent** (`sent_at` = now − 25 days) |
| 10 | Luis Romero | luis.romero@clearquote-demo.test | Investment / STR | Scottsdale, AZ, 85251, Maricopa | $410,000 | 25% | 5y | 765 | 3 | LOS-1000010 | Personal Name | none | 48 | — | priced | **option_selected** (`sent_at` = now − 3d, `viewed_at` = now − 2d) |

"Pipeline end status" is what the stage functions in Decision D1 produce (identical to what CQ-011's workflow must produce for the same inputs). "Seed end status" is what `demo-reset` leaves in the database after the fixture layer in Decision D2 runs on top for personas 9 and 10.

## Acceptance criteria

- [ ] AC1 — `make demo-reset` completes in under 60 s on a clean local stack, and every dollar/percent/rate value attached to a persona traces to `quote_engine` output computed from the seeded raw inputs (roadmap exit check). Evidence: `time make demo-reset` log + `seed/tests/test_personas_match_engine.py`.
- [ ] AC2 — All 10 personas exist after reset with the "Seed end status" from the table above. Test: `seed/tests/test_persona_statuses.py::test_persona_final_statuses_match_table`.
- [ ] AC3 — `provider_tax_rates`, `provider_rents`, `provider_str_revenue`, `provider_rate_sheet` and `provider_listings` (CQ-007's exact table names) have at least one row for each of the 10 persona markets; each of CQ-009's mock adapters returns a non-empty result for every persona. Test: `seed/tests/test_provider_rows_seeded.py`.
- [ ] AC4 — Exactly 2 `users` rows with role `LO`, 1 with role `Manager`, 1 with role `Admin` exist after reset, each with a bcrypt `password_hash` set (unusable until CQ-014 wires login). Test: `seed/tests/test_users_seeded.py`.
- [ ] AC5 — The background generator produces 190–210 `applications` rows using `random.Random(SEED_RNG_SEED)` with `SEED_RNG_SEED = 20260101`; running `make demo-reset` twice in a row produces identical per-status and per-LO counts. Test: `seed/tests/test_background_generator_determinism.py`.
- [ ] AC6 — Every persona has at least one `documents` row pointing to a MinIO object under bucket `clearquote-demo-docs`, and the stored file is watermarked "SAMPLE" (checked via filename suffix `-SAMPLE.pdf`/`-SAMPLE.png` and a burned-in watermark on the page). Test: `seed/tests/test_documents_watermarked.py`.
- [ ] AC7 — Grace Kim's application has `status = sent`, `quote_packages.sent_at` ≈ now − 25 days, and no `stale` transition until CQ-030's job runs; Luis Romero's has `status = option_selected`, `quote_packages.borrower_action` set, and at least one `activity_events` row plus one `outbox_emails` row from the send. Test: `seed/tests/test_persona_statuses.py::test_grace_and_luis_downstream_rows`.
- [ ] AC8 — The reference-sheet corrections in `system-design.md` (title at 0.7%, no mixed LTR/STR cashflow, no stray OB points) hold for every seeded quote — no seed value contradicts a golden test. Test: `seed/tests/test_personas_match_engine.py::test_no_reference_sheet_errors_reproduced`.

## Test plan

| Criterion | Test type | Test name / command |
| --- | --- | --- |
| AC1 | Timing + unit | `time make demo-reset`; `pytest seed/tests/test_personas_match_engine.py` |
| AC2 | Integration (DB) | `pytest seed/tests/test_persona_statuses.py::test_persona_final_statuses_match_table` |
| AC3 | Integration (DB) | `pytest seed/tests/test_provider_rows_seeded.py` |
| AC4 | Integration (DB) | `pytest seed/tests/test_users_seeded.py` |
| AC5 | Integration (DB), determinism | `pytest seed/tests/test_background_generator_determinism.py` |
| AC6 | Integration (MinIO) | `pytest seed/tests/test_documents_watermarked.py` |
| AC7 | Integration (DB) | `pytest seed/tests/test_persona_statuses.py::test_grace_and_luis_downstream_rows` |
| AC8 | Unit | `pytest seed/tests/test_personas_match_engine.py::test_no_reference_sheet_errors_reproduced` |

## Notes for the agent

- Follow the agent loop in `AGENTS.md`. Log small decisions in `plan.md`; raise big gaps in Kaneo.
- Package layout: `seed/personas/*.yaml` (one file per persona, fields per the table above plus `missing_fields: []` for the LOS defect), `seed/providers/*.yaml` (tax/rent/str/rate-sheet/listing fixtures keyed by market), `seed/users.yaml` (2 LO + 1 Manager + 1 Admin), `seed/generators/background_applications.py` (the ~200-app generator), `seed/generators/documents.py` (sample PDF/PNG generation + watermark + MinIO upload), `seed/loader.py` (reads YAML, calls service functions), `seed/reset.py` (the `demo-reset` entrypoint, invoked by the Makefile as `uv run python -m seed.reset`).
- Decision D1 (seed ↔ pipeline relationship): `demo-reset` does **not** start a real Temporal workflow. CQ-010 ships in wave 7, before CQ-011's workflow exists (wave 8), and running a live worker would blow the 60 s budget. Instead `seed/loader.py` calls the exact same stage service functions CQ-011 will later wrap as activities — `applications.service.import_from_los`, `applications.verification.service.run_and_persist`, `pricing.enrichment.service.enrich_pricing_fields`, `pricing.enrichment.service.validate_ob_required_fields`, `pricing.scenarios.service.auto_price`, `quotes.builder.service.draft_default_quote_set` — synchronously, in the same order the workflow will run them, and writes the same `application_status` and `activity_events` rows. This guarantees demo-reset and the real pipeline agree, and de-risks CQ-011 by giving it working service functions to wrap. CQ-011's spec references this table's "Pipeline end status" column as its own contract.
- Decision D2 (post-pipeline states): `sent` (persona 9) and `option_selected` (persona 10) are reached by features that ship long after P1 (CQ-019/020, CQ-024). `seed/loader.py` inserts the downstream rows directly — `quote_packages` (`sent_at`, `viewed_at`, `borrower_action`, `recommended_quote_id` pointing at an engine-produced quote), one `activity_events` row per hop (`quote.sent`, `quote.viewed`, `quote.option_selected`), and one `outbox_emails` row for the send — rather than calling not-yet-built send/select endpoints. The dollar figures inside those packages still come from the same `priced` quotes the pipeline produced; only the status/timestamps are fixture-authored.
- Decision D3 (fast mock adapters during seeding): CQ-009's mocks add 200–1,200 ms simulated latency per call; seeding 10 personas plus enrichment/pricing calls at that rate risks the 60 s budget. Add an env var `SEED_FAST_ADAPTERS=1` (read by the mock adapters, set by `seed/reset.py`) that skips the artificial delay without changing return values. Log this with CQ-009's owner if their spec doesn't already anticipate it.
- Decision D4 (background app markets): the ~200 generated applications draw only from the same 10 persona markets, so no additional `provider_*` fixtures are needed beyond AC3. Statuses are drawn to roughly match the dashboard tile shape in `system-design.md` (a mix across intake/verifying/needs_attention/ready_to_price/priced/sent/stale), LOs alternate between the 2 seeded LO users, occupancy/strategy mix is roughly 40% Primary / 40% LTR / 20% STR.
- Watermarking: generate simple PDFs/PNGs with a diagonal "SAMPLE" stamp (Pillow/ReportLab is fine, no need for WeasyPrint here — that's CQ-020's letter renderer) rather than sourcing real documents.
- **Question for the human** (do not guess): none — both gaps above were small enough to decide and log.
