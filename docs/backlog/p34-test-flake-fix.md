# P3/P4 backend test flake: activity sessions racing the test's connection

Branch `p34-test-flake-fix` off `phase-p3-p4`.

## Symptom

`asyncpg.exceptions._base.InterfaceError: cannot perform operation: another operation is in progress`
at teardown of a workflow test, then a cascade of errors in every later test (`cannot rollback; the transaction is not yet started`, `cannot use Connection.transaction() in a manually started transaction`, `savepoint "sa_savepoint_N" does not exist`), including `backend/tests/test_schema.py`. CI push run 36183565823 failed and PR run 36183570634 passed on the same commit eeb259a.

## Root cause

`backend/app/workflows/tests/conftest.py` binds every Temporal activity session to the test's own `db_session` connection, and the worker runs activities on the test's event loop. That makes the test and the activity two concurrent users of one asyncpg connection.

`wait_for_status` polls `applications.status` on that connection. Activities flush the status before they finish writing. `_fail_pricing_stage` flushes `needs_attention`, then commits `last_pipeline_stage`, then writes and commits `pipeline.pricing_blocked`. Because the flush is visible on the same connection, the poll could return while the activity was still writing. Two things then went wrong:

1. The test asserted too early. The first CI failure was `test_aisha_coleman_flagged_path_writes_4_events`, which got 3 events instead of 4 because `pipeline.pricing_blocked` was missing.
2. The test tore down under the running activity. `db_session`'s outer `rollback()` does not go through SQLAlchemy's `_execute_mutex` (only `execute` does), so it collided with the activity's in-flight statement and raised "another operation is in progress". The broken connection went back to the session-scoped engine's pool, and the stale activity kept using it, so every later test that checked it out failed.

A second form of the same race: if the test opened its savepoint while an activity's savepoint was open, the activity's `RELEASE` destroyed the test's savepoint too, which produced `savepoint ... does not exist`.

This is a test-harness bug. The production worker uses `AsyncSessionLocal`, where each activity gets its own pooled connection.

## Evidence

- CI log: the first failure is the AssertionError above. Every later E and F in `test_application_pipeline_personas.py`, `test_pipeline_stage_writes.py`, `test_resume_signal.py`, `test_retry_policy.py` and `backend/tests/*` is fallout from the poisoned connection.
- Local repro: `uv run pytest backend/app/workflows/tests backend/tests` (fixed order, `pytest-randomly` and `pytest-repeat` are not installed) failed **4/10** runs. The first failing test varied between the needs-attention tests.
- Instrumented run: a temporary counter on the patched `session_factory` logged `open_at_teardown=1` at teardown of `test_aisha_coleman_flagged_path_writes_4_events` and `test_kathleen_mcreynolds_ltr_tbd_property_prices`. Every other test logged 0.
- Deterministic RED: the new `test_wait_for_status_returns_only_after_the_writing_activity_closes` failed on the old conftest, because `wait_for_status` returned before the activity closed.

## Fix (test harness only, `backend/app/workflows/tests/conftest.py`)

- `ActivitySessionGate`, exposed as the `activity_session_gate` fixture:
  - An activity session counts as in flight from `__aenter__` to `__aexit__`, through a small `AsyncSession` subclass returned by `activities_session_factory`.
  - `test_turn()` waits until no activity session is open and blocks new ones until it exits.
- `wait_for_status` runs each poll inside `gate.test_turn()`. When it sees a matching status, the activity that wrote it has already closed, and the test's savepoint is always the outer one.
- Teardown guard: `bind_activities_to_test_session` waits for in-flight activity sessions to drain before `db_session` rolls back. If they have not drained after 10 s, it fails the leaking test by name instead of poisoning the rest of the run.

What stays the same: `backend/conftest.py`, production code, and the signatures of `wait_for_status`, `_wait_for_status` (new optional `gate` kwarg) and `activities_session_factory`. Existing and new (CQ-020) workflow tests get the gate automatically through `wait_for_status` and the autouse fixture. A test that queries `db_session` while a workflow may still be running should do so inside `async with activity_session_gate.test_turn():`.

Regression guard: `backend/app/workflows/tests/test_activity_session_gate.py`.

## Verification

- `uv run pytest backend/app/workflows/tests backend/tests`, fixed collection order (no random seeds, `pytest-randomly` is not installed): **0/20** failed after the fix, against **4/10** before.
- `make test`: backend 535 passed, seed 31 passed, frontend packages all passed.
- `make lint`: ruff, ruff format, mypy, eslint, tsc and prettier are all clean.
