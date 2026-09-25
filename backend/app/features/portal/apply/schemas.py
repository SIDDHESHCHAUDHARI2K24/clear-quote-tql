"""Request/response schemas for the apply API (CQ-032a; plan.md "Per-tab
data contract")."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel

from .validation import TabName

DocType = Literal["pay_stub", "w2", "bank_statement"]


class TabStatus(BaseModel):
    complete: bool


class DraftTabs(BaseModel):
    you: TabStatus
    property: TabStatus
    income: TabStatus
    consent: TabStatus


class ConsentTextOut(BaseModel):
    version: str
    text: str


class ApplyDraftOut(BaseModel):
    id: uuid.UUID
    email: str
    """The account email: tab 1's read-only, prefilled email."""
    current_tab: TabName
    """First tab that does not validate (`consent` when all do): where the
    wizard resumes (AC3)."""
    tabs: DraftTabs
    data: dict[str, Any]
    submitted_application_id: uuid.UUID | None
    consent: ConsentTextOut
    created_at: datetime
    updated_at: datetime


class DraftPatchRequest(BaseModel):
    tab: TabName
    data: dict[str, Any]


class DraftPatchResponse(BaseModel):
    draft: ApplyDraftOut
    tab: TabName
    tab_valid: bool
    field_errors: dict[str, str]
    """`{dotted.path: message}` for this tab; empty when it validates. The
    save has already happened either way."""


class DraftDocumentOut(BaseModel):
    id: uuid.UUID
    doc_type: DocType
    filename: str
    content_type: str
    size_bytes: int
    uploaded_at: datetime


class StateMetros(BaseModel):
    state: str
    metros: list[str]


class MetrosOut(BaseModel):
    """Tab 2's two-tier metro picker: states, each with its metros (both
    sorted). Only these names pass the `buy_box_metros` rule."""

    states: list[StateMetros]


class SubmitResponse(BaseModel):
    application_id: uuid.UUID
    draft_id: uuid.UUID
    status: Literal["intake"]
    assigned_lo_name: str
    pipeline_started: bool
