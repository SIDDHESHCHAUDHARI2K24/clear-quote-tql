"""`GET /api/v1/portal/reports/{token}` response shape (CQ-022 spec.md).

`PortalReportResponse` subclasses CQ-021's `ReportViewModel` rather than
redefining its fields: the frontend passes the response straight into
`<ReportPage viewModel={...}>` (packages/ui), whose props type is
`ReportViewModelData` (the api-client type generated from `ReportViewModel`)
-- extra fields on a wider response type are ignored by TypeScript's
structural typing, so no separate mapping step is needed.
"""

from __future__ import annotations

from typing import Any

from app.features.quotes.report.schemas import ReportViewModel


class PortalReportResponse(ReportViewModel):
    """`ReportViewModel` plus the two fields only a live request can answer:
    `borrower_action` (from `QuotePackageVersion.borrower_action`, `None`
    until CQ-024) and `newest_report_token` (set only when this version is
    superseded, per spec.md's "SupersededBanner ... a link to the newest
    version")."""

    borrower_action: dict[str, Any] | None = None
    newest_report_token: str | None = None
