// docs/backlog/CQ-028-verification-tabs/spec.md AC8: "Primary personas show
// employment, income and DTI; investment personas do not show DTI." This is
// the cross-tab gating test the plan.md T10-T16 task table designates
// (`VerificationTabs.gating.test.tsx`) -- each tab's own test file already
// covers its half; this file asserts the same gate holds for both the
// Credit tab's DTI and the Assets tab's employment/income in one place, and
// that neither ever infers the gate itself (both read it straight off the
// API's own `dti_applicable`/`income_applicable` booleans).
import type React from "react";

import { act, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const { getMock } = vi.hoisted(() => ({ getMock: vi.fn() }));

vi.mock("@cq/api-client", () => ({
  createApiClient: () => ({
    GET: getMock,
    PUT: vi.fn(),
    POST: vi.fn(),
    PATCH: vi.fn(),
    DELETE: vi.fn(),
  }),
}));

import { ToastProvider } from "@cq/ui";

import { WorkspaceProvider } from "../workspace";
import { makeSummary } from "../workspace/test-fixtures";
import { CreditTab } from "./credit/CreditTab";
import { AssetsTab } from "./assets/AssetsTab";
import { makeSection } from "./shared/test-fixtures";
import type { AssetsSummary, CreditSummary, SectionRecord, SectionResponse } from "./shared";

const APPLICATION_ID = "11111111-1111-1111-1111-111111111111";
const SUMMARY = makeSummary();

function renderReady(
  section: SectionResponse,
  Tab: (props: { applicationId: string }) => React.ReactElement,
) {
  getMock.mockImplementation((path: string) =>
    Promise.resolve({ data: path.includes("/summary") ? SUMMARY : section }),
  );
  return render(
    <ToastProvider>
      <WorkspaceProvider applicationId={APPLICATION_ID}>
        <Tab applicationId={APPLICATION_ID} />
      </WorkspaceProvider>
    </ToastProvider>,
  );
}

async function flush() {
  await act(async () => {
    await Promise.resolve();
  });
}

const EMPLOYMENT_RECORD: SectionRecord = {
  kind: "employment",
  id: "emp-1",
  role: null,
  manual: false,
  fields: [
    {
      field_key: "employment.emp-1.employer_name",
      label: "Employer",
      value: "Acme Corp",
      source: "encompass",
      overridden: false,
      editable: true,
    },
    {
      field_key: "employment.emp-1.monthly_income",
      label: "Monthly income",
      value: "8000.00",
      source: "encompass",
      overridden: false,
      editable: true,
    },
  ],
};

describe("Verification tabs -- primary vs investment gating (AC8)", () => {
  afterEach(() => {
    getMock.mockReset();
  });

  it("primary: Credit tab shows DTI as a percent (dti_applicable=true, dti_status=ok)", async () => {
    const credit: CreditSummary = {
      representative_fico: 715,
      fico_bracket: "700–719",
      pull_type: "soft_pull",
      pulled_at: "2026-01-05T00:00:00Z",
      liabilities_monthly_total: "410.00",
      dti_applicable: true,
      dti: "0.2839",
      dti_status: "ok",
      consent: null,
    };
    renderReady(makeSection({ tab: "credit", credit, records: [] }), CreditTab);
    await flush();
    expect(screen.getByText(/DTI/)).toBeInTheDocument();
    expect(screen.getByText("28.4%")).toBeInTheDocument();
  });

  it("investment: Credit tab shows no DTI row at all (dti_applicable=false)", async () => {
    const credit: CreditSummary = {
      representative_fico: 715,
      fico_bracket: "700–719",
      pull_type: "soft_pull",
      pulled_at: "2026-01-05T00:00:00Z",
      liabilities_monthly_total: "410.00",
      dti_applicable: false,
      dti: null,
      dti_status: "not_applicable",
      consent: null,
    };
    renderReady(makeSection({ tab: "credit", credit, records: [] }), CreditTab);
    await flush();
    expect(screen.queryByText(/DTI/)).not.toBeInTheDocument();
  });

  it("primary: Assets tab shows employment and total monthly income (income_applicable=true)", async () => {
    const assets: AssetsSummary = {
      verified_assets_total: "15000.00",
      reserves_months: 2,
      reserves_required: "3200.00",
      cash_to_close: "40000.00",
      required_funds: "43200.00",
      status: "sufficient",
      income_applicable: true,
      monthly_income_total: "8000.00",
      documents: [],
    };
    renderReady(makeSection({ tab: "assets", assets, records: [EMPLOYMENT_RECORD] }), AssetsTab);
    await flush();
    expect(screen.getAllByText("Acme Corp").length).toBeGreaterThan(0);
    expect(screen.getByText("Total monthly income:", { exact: false })).toBeInTheDocument();
  });

  it("investment: Assets tab shows no employment or income UI (income_applicable=false)", async () => {
    const assets: AssetsSummary = {
      verified_assets_total: "15000.00",
      reserves_months: 6,
      reserves_required: "9600.00",
      cash_to_close: "40000.00",
      required_funds: "49600.00",
      status: "sufficient",
      income_applicable: false,
      monthly_income_total: null,
      documents: [],
    };
    // Matches the real API's own behavior (service.py's `_assets` only adds
    // employment records when `income_applicable`), not just the tab's own
    // filter -- no employment record is even present here.
    renderReady(makeSection({ tab: "assets", assets, records: [] }), AssetsTab);
    await flush();
    expect(screen.queryByText("Acme Corp")).not.toBeInTheDocument();
    expect(screen.queryByText(/monthly income/i)).not.toBeInTheDocument();
  });
});
