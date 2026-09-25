"""`stage_and_label` (CQ-031 spec.md's mapping table) -- pure unit tests,
no DB. `test_router.py` covers the rest of `service.py` (next_action
resolution, draft entries, LO contact) through the real endpoint."""

from __future__ import annotations

import pytest

from app.core.enums import ApplicationStatus
from app.features.portal.home.schemas import PortalStage
from app.features.portal.home.service import stage_and_label

_LO_FIRST_NAME = "Jordan"


@pytest.mark.parametrize(
    "status,expected_stage,expected_label",
    [
        (ApplicationStatus.INTAKE, PortalStage.APPLIED, "Application received"),
        (ApplicationStatus.VERIFYING, PortalStage.APPLIED, "Application received"),
        (ApplicationStatus.NEEDS_ATTENTION, PortalStage.APPLIED, "Application received"),
        (ApplicationStatus.READY_TO_PRICE, PortalStage.APPLIED, "Application received"),
        (
            ApplicationStatus.PRICED,
            PortalStage.IN_REVIEW,
            "Your loan officer is reviewing your numbers",
        ),
        (ApplicationStatus.SENT, PortalStage.PREAPPROVED, "Your pre-approval is ready"),
        (ApplicationStatus.VIEWED, PortalStage.PREAPPROVED, "Your pre-approval is ready"),
        (ApplicationStatus.INQUIRY, PortalStage.PREAPPROVED, "Your pre-approval is ready"),
        (
            ApplicationStatus.OPTION_SELECTED,
            PortalStage.OPTION_SELECTED,
            f"You chose an option — {_LO_FIRST_NAME} will be in touch",
        ),
        (ApplicationStatus.WITHDRAWN, PortalStage.CLOSED, "This application is closed"),
        (ApplicationStatus.CLOSED, PortalStage.CLOSED, "This application is closed"),
    ],
)
def test_stage_and_label_status_independent_of_has_ever_sent(
    status: ApplicationStatus, expected_stage: PortalStage, expected_label: str
) -> None:
    """Every status except `stale` maps the same way regardless of
    `has_ever_sent` -- only `stale` branches on it."""
    for has_ever_sent in (True, False):
        stage, label = stage_and_label(
            status, has_ever_sent=has_ever_sent, lo_first_name=_LO_FIRST_NAME
        )
        assert (stage, label) == (expected_stage, expected_label)


def test_stale_never_sent_maps_to_in_review() -> None:
    stage, label = stage_and_label(
        ApplicationStatus.STALE, has_ever_sent=False, lo_first_name=_LO_FIRST_NAME
    )
    assert stage is PortalStage.IN_REVIEW
    assert label == "Your loan officer is reviewing your numbers"


def test_stale_after_a_send_maps_to_preapproved() -> None:
    stage, label = stage_and_label(
        ApplicationStatus.STALE, has_ever_sent=True, lo_first_name=_LO_FIRST_NAME
    )
    assert stage is PortalStage.PREAPPROVED
    assert label == "Your pre-approval is ready"


def test_no_internal_vocabulary_in_any_label() -> None:
    """AC2, at the mapping-function level: none of the borrower-facing
    labels this function can produce contain "attention", "flag" or
    "error"."""
    banned = ("attention", "flag", "error")
    for status in ApplicationStatus:
        for has_ever_sent in (True, False):
            _, label = stage_and_label(
                status, has_ever_sent=has_ever_sent, lo_first_name=_LO_FIRST_NAME
            )
            lowered = label.lower()
            for word in banned:
                assert word not in lowered, f"{status}: {label!r} contains {word!r}"
