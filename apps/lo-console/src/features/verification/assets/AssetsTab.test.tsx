import { act, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const { getMock, patchMock } = vi.hoisted(() => ({ getMock: vi.fn(), patchMock: vi.fn() }));

vi.mock("@cq/api-client", () => ({
  createApiClient: () => ({
    GET: getMock,
    PUT: vi.fn(),
    POST: vi.fn(),
    PATCH: patchMock,
    DELETE: vi.fn(),
  }),
}));

import { ToastProvider } from "@cq/ui";

import { makeSummary } from "../../workspace/test-fixtures";
import { WorkspaceProvider } from "../../workspace";
import { makeSection } from "../shared/test-fixtures";
import type { AssetsSummary, SectionRecord, SectionResponse } from "../shared";
import { AssetsTab } from "./AssetsTab";

const APPLICATION_ID = "11111111-1111-1111-1111-111111111111";
const SUMMARY = makeSummary();

const ASSET_RECORD: SectionRecord = {
  kind: "asset",
  id: "asset-1",
  role: null,
  manual: false,
  fields: [
    {
      field_key: "assets.asset-1.account_type",
      label: "Account type",
      value: "Checking",
      source: "encompass",
      overridden: false,
      editable: true,
    },
    {
      field_key: "assets.asset-1.institution",
      label: "Institution",
      value: "Chase",
      source: "encompass",
      overridden: false,
      editable: true,
    },
    {
      field_key: "assets.asset-1.verified_amount",
      label: "Verified amount",
      value: "15000.00",
      source: "encompass",
      overridden: false,
      editable: true,
    },
  ],
};

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
    {
      field_key: "employment.emp-1.self_employed",
      label: "Self-employed",
      value: false,
      source: "encompass",
      overridden: false,
      editable: true,
    },
  ],
};

function baseAssets(overrides: Partial<AssetsSummary> = {}): AssetsSummary {
  return {
    verified_assets_total: "15000.00",
    reserves_months: 6,
    reserves_required: "9000.00",
    cash_to_close: "20000.00",
    required_funds: "29000.00",
    status: "sufficient",
    income_applicable: true,
    monthly_income_total: "8000.00",
    documents: [{ id: "doc-1", doc_type: "pay_stub", received: false, received_at: null }],
    ...overrides,
  };
}

function mockSectionGet(section: SectionResponse) {
  getMock.mockImplementation((path: string) =>
    Promise.resolve({ data: path.includes("/summary") ? SUMMARY : section }),
  );
}

function renderTab() {
  render(
    <ToastProvider>
      <WorkspaceProvider applicationId={APPLICATION_ID}>
        <AssetsTab applicationId={APPLICATION_ID} />
      </WorkspaceProvider>
    </ToastProvider>,
  );
}

// docs/backlog/CQ-028-verification-tabs/spec.md AC8: "Primary personas show
// employment, income and DTI; investment personas do not show DTI" -- the
// Assets tab's half of that gate is employment + monthly income total,
// driven by `section.assets.income_applicable`.
describe("AssetsTab (docs/backlog/CQ-028-verification-tabs/spec.md AC8, row 4)", () => {
  afterEach(() => {
    getMock.mockReset();
    patchMock.mockReset();
  });

  it("primary loan (income_applicable: true): renders employment fields and monthly income total", async () => {
    mockSectionGet(
      makeSection({
        records: [ASSET_RECORD, EMPLOYMENT_RECORD],
        assets: baseAssets({ income_applicable: true }),
      }),
    );

    renderTab();
    await act(async () => {
      await Promise.resolve();
    });

    expect(screen.getAllByText("Acme Corp").length).toBeGreaterThan(0);
    expect(screen.getByText("Employer")).toBeInTheDocument();
    expect(screen.getByText(/Total monthly income/)).toBeInTheDocument();
  });

  it("investment loan (income_applicable: false): renders no employment/income UI at all", async () => {
    // Real API behavior: the backend itself omits employment records for
    // investment loans, so `records` carries no employment kind here.
    mockSectionGet(
      makeSection({
        occupancy: "investment",
        records: [ASSET_RECORD],
        assets: baseAssets({ income_applicable: false, monthly_income_total: null }),
      }),
    );

    renderTab();
    await act(async () => {
      await Promise.resolve();
    });

    expect(screen.queryByText("Acme Corp")).not.toBeInTheDocument();
    expect(screen.queryByText(/Total monthly income/)).not.toBeInTheDocument();
    expect(screen.queryByText("Employer")).not.toBeInTheDocument();
  });

  it.each([
    ["sufficient", "Sufficient"],
    ["insufficient", "Insufficient"],
    ["awaiting_pricing", "Awaiting pricing"],
  ] as const)("renders the %s sufficiency state distinctly", async (status, expectedText) => {
    mockSectionGet(
      makeSection({
        records: [ASSET_RECORD],
        assets: baseAssets({
          status,
          reserves_required: status === "awaiting_pricing" ? null : "9000.00",
        }),
      }),
    );

    renderTab();
    await act(async () => {
      await Promise.resolve();
    });

    expect(screen.getByText(expectedText)).toBeInTheDocument();
  });

  it('"Mark received" calls patchDocument with the doc id and true, then flips to "Mark not received"', async () => {
    const section = makeSection({
      records: [ASSET_RECORD],
      assets: baseAssets(),
    });
    mockSectionGet(section);
    patchMock.mockResolvedValue({
      data: makeSection({
        records: [ASSET_RECORD],
        assets: baseAssets({
          documents: [
            { id: "doc-1", doc_type: "pay_stub", received: true, received_at: "2026-09-25" },
          ],
        }),
      }),
    });

    renderTab();
    await act(async () => {
      await Promise.resolve();
    });

    expect(screen.getByText("pay stub")).toBeInTheDocument();
    const button = screen.getByRole("button", { name: "Mark received" });

    await act(async () => {
      button.click();
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(patchMock).toHaveBeenCalledWith(
      "/api/v1/applications/{application_id}/documents/{document_id}",
      expect.objectContaining({
        params: { path: { application_id: APPLICATION_ID, document_id: "doc-1" } },
        body: { received: true },
      }),
    );
    expect(await screen.findByRole("button", { name: "Mark not received" })).toBeInTheDocument();
  });
});
