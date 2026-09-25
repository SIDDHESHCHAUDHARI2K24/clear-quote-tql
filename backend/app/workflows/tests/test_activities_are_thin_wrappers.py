"""AC2: every activity calls its wrapped service function exactly once with
`application_id` and returns its result unchanged, except `verify_
application`, which additionally derives `passed` from the returned
`list[RuleResult]` (spec.md Contracts) — asserted by dedicated tests below,
not the generic spy pattern.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from unittest.mock import AsyncMock

import pytest

from app.core.enums import ApplicationTab, FlagSeverity
from app.features.applications.models import Application
from app.features.applications.verification.schemas import RuleResult
from app.features.applications.verification.service import VerificationRunResult
from app.features.pricing.enrichment.service import EnrichmentResult
from app.features.pricing.scenarios.service import PricingResult
from app.features.quotes.builder.service import QuoteSetResult
from app.workflows import activities
from app.workflows.tests.conftest import FakeImportResult, install_import_from_los


async def test_import_application_is_a_thin_wrapper(
    monkeypatch: pytest.MonkeyPatch,
    make_persona_application: Callable[..., Awaitable[Application]],
) -> None:
    application = await make_persona_application()
    result = FakeImportResult(application_id=application.id, parties_created=2)
    spy = AsyncMock(return_value=result)
    install_import_from_los(monkeypatch, spy)

    returned = await activities.import_application(str(application.id))

    assert spy.await_count == 1
    assert spy.await_args is not None
    assert spy.await_args.args[0] == application.id
    assert returned is result


async def test_verify_application_is_a_thin_wrapper(
    monkeypatch: pytest.MonkeyPatch,
    make_persona_application: Callable[..., Awaitable[Application]],
) -> None:
    application = await make_persona_application()
    run_result = VerificationRunResult(rule_results=[])
    spy = AsyncMock(return_value=run_result)
    monkeypatch.setattr(activities, "run_and_persist", spy)

    returned = await activities.verify_application(str(application.id))

    assert spy.await_count == 1
    assert spy.await_args is not None
    assert spy.await_args.args[0] == application.id
    assert returned.rule_results == run_result.rule_results


async def test_enrich_application_is_a_thin_wrapper(
    monkeypatch: pytest.MonkeyPatch,
    make_persona_application: Callable[..., Awaitable[Application]],
) -> None:
    application = await make_persona_application()
    result = EnrichmentResult(field_keys_written=["property_tax_annual_rate"])
    spy = AsyncMock(return_value=result)
    monkeypatch.setattr(activities, "enrich_pricing_fields", spy)

    returned = await activities.enrich_application(str(application.id))

    assert spy.await_count == 1
    assert spy.await_args is not None
    assert spy.await_args.args[1] == application.id
    assert returned == result


async def test_validate_pricing_inputs_is_a_thin_wrapper(
    monkeypatch: pytest.MonkeyPatch,
    make_persona_application: Callable[..., Awaitable[Application]],
) -> None:
    application = await make_persona_application()
    spy = AsyncMock(return_value=True)
    monkeypatch.setattr(activities, "validate_ob_required_fields", spy)

    returned = await activities.validate_pricing_inputs(str(application.id))

    assert spy.await_count == 1
    assert spy.await_args is not None
    assert spy.await_args.args[1] == application.id
    assert returned is True


async def test_auto_price_application_is_a_thin_wrapper(
    monkeypatch: pytest.MonkeyPatch,
    make_persona_application: Callable[..., Awaitable[Application]],
) -> None:
    application = await make_persona_application()
    result = PricingResult(scenario_ids=[uuid.uuid4()], quote_ids=[uuid.uuid4()])
    spy = AsyncMock(return_value=result)
    monkeypatch.setattr(activities, "auto_price", spy)

    returned = await activities.auto_price_application(str(application.id))

    assert spy.await_count == 1
    assert spy.await_args is not None
    assert spy.await_args.args[1] == application.id
    assert returned == result


async def test_draft_quote_set_is_a_thin_wrapper(
    monkeypatch: pytest.MonkeyPatch,
    make_persona_application: Callable[..., Awaitable[Application]],
) -> None:
    application = await make_persona_application()
    pricing_result = PricingResult(scenario_ids=[uuid.uuid4()], quote_ids=[uuid.uuid4()])
    result = QuoteSetResult(quote_ids=pricing_result.quote_ids)
    spy = AsyncMock(return_value=result)
    monkeypatch.setattr(activities, "draft_default_quote_set", spy)

    returned = await activities.draft_quote_set(str(application.id), pricing_result)

    assert spy.await_count == 1
    assert spy.await_args is not None
    assert spy.await_args.args[1] == application.id
    assert spy.await_args.args[2] is pricing_result
    assert returned == result


@pytest.mark.parametrize(
    ("rule_results", "expected_passed"),
    [
        ([], True),
        (
            [
                RuleResult(
                    rule_id="phone_copy",
                    tab=ApplicationTab.BORROWERS,
                    field_key="borrower_home_phone",
                    severity=FlagSeverity.INFO,
                    passed=True,
                    message="ok",
                )
            ],
            True,
        ),
        (
            [
                RuleResult(
                    rule_id="dti_primary",
                    tab=ApplicationTab.CREDIT,
                    field_key="dti_ratio",
                    severity=FlagSeverity.WARNING,
                    passed=False,
                    message="high dti",
                )
            ],
            True,
        ),
        (
            [
                RuleResult(
                    rule_id="housing_history_24mo",
                    tab=ApplicationTab.HOUSING,
                    field_key="current_residence_years",
                    severity=FlagSeverity.BLOCKING,
                    passed=False,
                    message="short",
                )
            ],
            False,
        ),
        (
            [
                RuleResult(
                    rule_id="ssn_format",
                    tab=ApplicationTab.BORROWERS,
                    field_key="borrower_ssn",
                    severity=FlagSeverity.BLOCKING,
                    passed=True,
                    message="ok",
                ),
                RuleResult(
                    rule_id="housing_history_24mo",
                    tab=ApplicationTab.HOUSING,
                    field_key="current_residence_years",
                    severity=FlagSeverity.BLOCKING,
                    passed=False,
                    message="short",
                ),
            ],
            False,
        ),
    ],
)
async def test_verify_application_derives_passed_per_spec_rule(
    monkeypatch: pytest.MonkeyPatch,
    make_persona_application: Callable[..., Awaitable[Application]],
    rule_results: list[RuleResult],
    expected_passed: bool,
) -> None:
    """AC2's dedicated test: `passed` is `True` unless any `RuleResult` has
    `severity == FlagSeverity.blocking and passed == False` — a pure
    derivation of CQ-012's own severity semantics, not a second rule
    engine."""
    application = await make_persona_application()
    run_result = VerificationRunResult(rule_results=rule_results)
    monkeypatch.setattr(activities, "run_and_persist", AsyncMock(return_value=run_result))

    result = await activities.verify_application(str(application.id))

    assert result.passed is expected_passed
