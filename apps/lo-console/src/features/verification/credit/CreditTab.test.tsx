import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const { getMock, postMock } = vi.hoisted(() => ({ getMock: vi.fn(), postMock: vi.fn() }));

vi.mock("@cq/api-client", () => ({
  createApiClient: () => ({
    GET: getMock,
    PUT: vi.fn(),
    POST: postMock,
    PATCH: vi.fn(),
    DELETE: vi.fn(),
  }),
}));

import { ToastProvider } from "@cq/ui";

import { WorkspaceProvider } from "../../workspace";
import { makeSummary } from "../../workspace/test-fixtures";
import { makeSection } from "../shared/test-fixtures";
import type { CreditSummary, SectionRecord, SectionResponse } from "../shared";
import { CreditTab } from "./CreditTab";

const APPLICATION_ID = "11111111-1111-1111-1111-111111111111";
const SUMMARY = makeSummary();

function mockGetSection(section: SectionResponse) {
  getMock.mockImplementation((path: string) =>
    Promise.resolve({ data: path.includes("/summary") ? SUMMARY : section }),
  );
}

async function flush() {
  await act(async () => {
    await Promise.resolve();
  });
}

function renderTab() {
  return render(
    <ToastProvider>
      <WorkspaceProvider applicationId={APPLICATION_ID}>
        <CreditTab applicationId={APPLICATION_ID} />
      </WorkspaceProvider>
    </ToastProvider>,
  );
}

const BASE_CREDIT: CreditSummary = {
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

const LIABILITY_RECORD: SectionRecord = {
  kind: "liability",
  id: "liab-1",
  role: null,
  manual: false,
  fields: [
    {
      field_key: "liabilities.liab-1.creditor_name",
      label: "Creditor",
      value: "Chase",
      source: "credit_bureau",
      overridden: false,
      editable: true,
    },
    {
      field_key: "liabilities.liab-1.account_type",
      label: "Account type",
      value: "Credit card",
      source: "credit_bureau",
      overridden: false,
      editable: true,
    },
    {
      field_key: "liabilities.liab-1.monthly_payment",
      label: "Monthly payment",
      value: "150.00",
      source: "credit_bureau",
      overridden: false,
      editable: true,
    },
    {
      field_key: "liabilities.liab-1.balance",
      label: "Balance",
      value: "3200.00",
      source: "credit_bureau",
      overridden: false,
      editable: true,
    },
  ],
};

function consent(overrides: Partial<NonNullable<CreditSummary["consent"]>>) {
  return {
    id: "consent-1",
    status: "pending" as const,
    requested_at: "2026-01-01T00:00:00Z",
    requested_by: "lo-1",
    expires_at: null,
    decided_at: null,
    decline_reason: null,
    fico_after_pull: null,
    ...overrides,
  };
}

describe("CreditTab (docs/backlog/CQ-028-verification-tabs/spec.md)", () => {
  afterEach(() => {
    getMock.mockReset();
    postMock.mockReset();
  });

  it("AC8: renders DTI as a formatted percent for a primary loan (dti_applicable=true)", async () => {
    mockGetSection(makeSection({ credit: BASE_CREDIT, records: [] }));
    renderTab();
    await flush();

    expect(screen.getByText("28.4%")).toBeInTheDocument();
    expect(screen.queryByText("0.2839")).not.toBeInTheDocument();
  });

  it("AC8: renders no DTI row/text at all for an investment loan (dti_applicable=false)", async () => {
    mockGetSection(
      makeSection({
        occupancy: "investment",
        credit: { ...BASE_CREDIT, dti_applicable: false, dti: null, dti_status: "not_applicable" },
        records: [],
      }),
    );
    renderTab();
    await flush();

    expect(screen.queryByText(/DTI/)).not.toBeInTheDocument();
  });

  it("AC4: 'Import liabilities' calls importLiabilities and applies the returned section", async () => {
    mockGetSection(makeSection({ credit: BASE_CREDIT, records: [] }));
    postMock.mockImplementation((path: string) => {
      if (path.includes("import-liabilities")) {
        return Promise.resolve({
          data: makeSection({ credit: BASE_CREDIT, records: [LIABILITY_RECORD] }),
        });
      }
      return Promise.resolve({ data: undefined, error: undefined });
    });

    renderTab();
    await flush();

    fireEvent.click(screen.getByText("Import liabilities"));
    await flush();

    expect(postMock).toHaveBeenCalledWith(
      expect.stringContaining("import-liabilities"),
      expect.anything(),
    );
    // "Chase" renders twice (the Card's title and the creditor_name field's
    // value) -- assert on the account-type field, which only appears once.
    expect(screen.getByText("Credit card")).toBeInTheDocument();
  });

  it("AC5: 'Request hard pull' success calls requestHardPull and applies data.section", async () => {
    mockGetSection(makeSection({ credit: BASE_CREDIT, records: [] }));
    postMock.mockImplementation((path: string) => {
      if (path.includes("hard-pull-request")) {
        return Promise.resolve({
          data: {
            consent: consent({ status: "pending" }),
            section: makeSection({
              credit: { ...BASE_CREDIT, consent: consent({ status: "pending" }) },
              records: [],
            }),
          },
        });
      }
      return Promise.resolve({ data: undefined, error: undefined });
    });

    renderTab();
    await flush();

    fireEvent.click(screen.getByText("Request hard pull"));
    await flush();

    expect(postMock).toHaveBeenCalledWith(
      expect.stringContaining("hard-pull-request"),
      expect.anything(),
    );
    expect(screen.getByText("Awaiting borrower consent")).toBeInTheDocument();
  });

  it("AC5: a 409 while a request is already pending shows the backend's error message", async () => {
    mockGetSection(makeSection({ credit: BASE_CREDIT, records: [] }));
    postMock.mockImplementation((path: string) => {
      if (path.includes("hard-pull-request")) {
        return Promise.resolve({
          error: {
            error: {
              code: "CONFLICT",
              message: "A hard-pull consent request is already pending for this borrower.",
            },
          },
        });
      }
      return Promise.resolve({ data: undefined, error: undefined });
    });

    renderTab();
    await flush();

    fireEvent.click(screen.getByText("Request hard pull"));
    await flush();

    expect(screen.getByText(/already pending/)).toBeInTheDocument();
  });

  it("E11: shows 'Awaiting borrower consent' while status is pending", async () => {
    mockGetSection(
      makeSection({
        credit: { ...BASE_CREDIT, consent: consent({ status: "pending" }) },
        records: [],
      }),
    );
    renderTab();
    await flush();

    expect(screen.getByText("Awaiting borrower consent")).toBeInTheDocument();
  });

  it("E11: shows 'Authorized {date} — hard pull complete, FICO {score}' once accepted", async () => {
    mockGetSection(
      makeSection({
        credit: {
          ...BASE_CREDIT,
          consent: consent({
            status: "accepted",
            decided_at: "2026-01-03T00:00:00Z",
            fico_after_pull: 702,
          }),
        },
        records: [],
      }),
    );
    renderTab();
    await flush();

    expect(screen.getByText(/Authorized .* — hard pull complete, FICO 702/)).toBeInTheDocument();
  });

  it("E11: shows 'Declined {date}: {reason}' once declined", async () => {
    mockGetSection(
      makeSection({
        credit: {
          ...BASE_CREDIT,
          consent: consent({
            status: "declined",
            decided_at: "2026-01-04T00:00:00Z",
            decline_reason: "Borrower declined",
          }),
        },
        records: [],
      }),
    );
    renderTab();
    await flush();

    expect(screen.getByText(/Declined .*: Borrower declined/)).toBeInTheDocument();
  });

  it("E11: shows 'Expired {date}' once expired, still allowing a new request", async () => {
    mockGetSection(
      makeSection({
        credit: {
          ...BASE_CREDIT,
          consent: consent({ status: "expired", expires_at: "2026-01-08T00:00:00Z" }),
        },
        records: [],
      }),
    );
    renderTab();
    await flush();

    expect(screen.getByText(/Expired/)).toBeInTheDocument();
    expect(screen.getByText("Request hard pull").closest("button")).not.toBeDisabled();
  });
});
