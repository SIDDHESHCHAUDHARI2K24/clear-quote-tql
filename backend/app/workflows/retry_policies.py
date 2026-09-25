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
