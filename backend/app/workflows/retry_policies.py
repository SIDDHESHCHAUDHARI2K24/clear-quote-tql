"""Retry policies shared by `application_pipeline.py` and its tests
(plan.md #7) — tests import these same objects so they exercise the real
configured policy, not a re-implementation.

`NON_RETRYABLE_ERROR_TYPES` matches CQ-009's `app.integrations.common.
errors.PricingValidationError`/`ProviderUnavailableError` **by class name**
(Temporal's `RetryPolicy.non_retryable_error_types` matches on the string
type name of the failure), per spec.md "Retry policy": these are
business/demo-control outcomes, not transient faults, so the workflow
catches them on the first attempt.
"""

from __future__ import annotations

from datetime import timedelta

from temporalio.common import RetryPolicy

NON_RETRYABLE_ERROR_TYPES = ["PricingValidationError", "ProviderUnavailableError"]

# A generous real-wall-clock ceiling (mocks simulate at most ~1.2s latency
# in production, and INTEGRATION_LATENCY_ENABLED=false disables that in
# tests) -- kept high rather than tight so a loaded CI/dev machine doesn't
# spuriously time out an activity that never actually stalled.
ACTIVITY_TIMEOUT = timedelta(seconds=60)

# `import_application`/`enrich_application`: transient mock-adapter latency
# gets a tight, bounded retry schedule (spec.md "Retry policy").
IMPORT_ENRICH_RETRY_POLICY = RetryPolicy(
    initial_interval=timedelta(seconds=1),
    backoff_coefficient=2.0,
    maximum_interval=timedelta(seconds=30),
    maximum_attempts=3,
    non_retryable_error_types=NON_RETRYABLE_ERROR_TYPES,
)

# `verify_application`, `validate_pricing_inputs`, `auto_price_application`,
# `draft_quote_set`: spec.md only pins the non-retryable list for these —
# every other field stays Temporal's default.
DEFAULT_RETRY_POLICY = RetryPolicy(non_retryable_error_types=NON_RETRYABLE_ERROR_TYPES)

# CQ-020 (plan.md Decision 15): the SendQuotePackage activities. Bounded so a
# broken SMTP/MinIO ends in `send_status = failed` instead of retrying
# forever; `PackageNotReadyError` (Freeze found blockers) and
# `SendSupersededError` (a newer send owns the package, Decision 22) are
# final. CRM's
# `ProviderUnavailableError` stays retryable here, unlike the pipeline: the
# email has already gone out by the Record step.
SEND_RETRY_POLICY = RetryPolicy(
    initial_interval=timedelta(seconds=1),
    backoff_coefficient=2.0,
    maximum_interval=timedelta(seconds=30),
    maximum_attempts=5,
    non_retryable_error_types=["PackageNotReadyError", "SendSupersededError"],
)

# CQ-020 (PR #30 re-review minor 3): a per-attempt ceiling for freeze/
# render/email/record, tighter than the shared `ACTIVITY_TIMEOUT` (60s). At
# `SEND_RETRY_POLICY`'s 5 attempts, the old 60s ceiling let one activity's
# worst-case retry budget alone run 5*60 + (1+2+4+8) = 315s; four activities
# in the same run could add up to ~1260s (21 min) -- longer than
# `SEND_EXECUTION_TIMEOUT` (10 min), so a persistently failing SMTP/MinIO
# step could be timed out by Temporal *before* the workflow's except block
# ever runs `mark_send_failed`, leaving the package stuck "in flight"
# instead of `failed`. At 20s, the same worst case is 5*20 + 15 = 115s per
# activity, 460s (~7.7 min) for all four -- comfortably under the execution
# timeout. `test_send_execution_timeout_exceeds_the_worst_case_retry_budget`
# guards the invariant.
SEND_ACTIVITY_TIMEOUT = timedelta(seconds=20)

# CQ-020 (plan.md Decision 23): a send that hasn't finished in 10 minutes
# (no worker running, a worker stuck) is ended by Temporal, so the package
# can't stay "sending" forever; the API then reports it `failed`. Must stay
# above the worst-case retry budget of the send activities above (see
# `SEND_ACTIVITY_TIMEOUT`), or Temporal can time the whole workflow out
# before `mark_send_failed` gets to run.
SEND_EXECUTION_TIMEOUT = timedelta(minutes=10)
