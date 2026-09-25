import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const { getMock, putMock, postMock } = vi.hoisted(() => ({
  getMock: vi.fn(),
  putMock: vi.fn(),
  postMock: vi.fn(),
}));

vi.mock("@cq/api-client", () => ({
  createApiClient: () => ({
    GET: getMock,
    PUT: putMock,
    POST: postMock,
    PATCH: vi.fn(),
    DELETE: vi.fn(),
  }),
}));

import { ToastProvider } from "@cq/ui";

import { makeSummary } from "../../workspace/test-fixtures";
import { WorkspaceProvider } from "../../workspace";
import { makeSection } from "../shared/test-fixtures";
import type { SectionField, SectionRecord, SectionResponse } from "../shared";
import { BorrowersTab } from "./BorrowersTab";

const APPLICATION_ID = "11111111-1111-1111-1111-111111111111";
const SUMMARY = makeSummary();

function field(overrides: Partial<SectionField>): SectionField {
  return {
    field_key: "borrower_first_name",
    label: "First name",
    value: null,
    source: "encompass",
    overridden: false,
    editable: true,
    ...overrides,
  };
}

function borrowerParty(overrides: Partial<SectionField>[] = []): SectionRecord {
  const base: SectionField[] = [
    field({ field_key: "borrower_first_name", label: "First name", value: "Priya" }),
    field({ field_key: "borrower_last_name", label: "Last name", value: "Nair" }),
    field({ field_key: "borrower_ssn", label: "SSN", value: "***-**-1234" }),
    field({
      field_key: "borrower_dob",
      label: "Date of birth",
      value: "1990-01-01",
      source: "encompass",
    }),
    field({
      field_key: "borrower_marital_status",
      label: "Marital status",
      value: "married",
      source: "lo_entry",
    }),
    field({
      field_key: "borrower_dependents_count",
      label: "Dependents",
      value: 1,
      source: "lo_entry",
    }),
    field({ field_key: "borrower_email", label: "Email", value: "priya@example.com" }),
    field({ field_key: "borrower_cell_phone", label: "Cell phone", value: "6145557007" }),
    field({ field_key: "borrower_home_phone", label: "Home phone", value: null }),
    field({ field_key: "borrower_work_phone", label: "Work phone", value: null }),
    field({
      field_key: "borrower_business_vesting",
      label: "Vesting",
      value: "personal_name",
      source: "lo_entry",
    }),
    field({ field_key: "borrower_llc_entity_name", label: "LLC name", value: null }),
    field({
      field_key: "borrower_no_co_applicant_check",
      label: "No co-applicant",
      value: false,
      source: "lo_entry",
    }),
  ];
  const merged = base.map((f) => {
    const override = overrides.find((o) => o.field_key === f.field_key);
    return override ? { ...f, ...override } : f;
  });
  return {
    kind: "party",
    id: "party-borrower-1",
    role: "borrower",
    manual: false,
    fields: merged,
  };
}

function mockGetSection(section: SectionResponse) {
  getMock.mockImplementation((path: string) => {
    if (path.includes("/summary"))
      return Promise.resolve({ data: SUMMARY, response: { status: 200 } });
    return Promise.resolve({ data: section, response: { status: 200 } });
  });
}

function renderTab() {
  return render(
    <ToastProvider>
      <WorkspaceProvider applicationId={APPLICATION_ID}>
        <BorrowersTab applicationId={APPLICATION_ID} />
      </WorkspaceProvider>
    </ToastProvider>,
  );
}

describe("BorrowersTab (docs/backlog/CQ-028-verification-tabs)", () => {
  afterEach(() => {
    getMock.mockReset();
    putMock.mockReset();
    postMock.mockReset();
  });

  it("renders the borrower's fields", async () => {
    mockGetSection(makeSection({ records: [borrowerParty()] }));
    renderTab();

    await act(async () => {
      await Promise.resolve();
    });

    expect(screen.getByText("Borrower")).toBeInTheDocument();
    expect(screen.getByText("First name")).toBeInTheDocument();
    expect(screen.getByText("Priya")).toBeInTheDocument();
    expect(screen.getByText("Nair")).toBeInTheDocument();
    expect(screen.getByText("6145557007")).toBeInTheDocument();
  });

  it("edits a field and applies the returned section", async () => {
    const section = makeSection({ records: [borrowerParty()] });
    mockGetSection(section);
    putMock.mockResolvedValue({
      data: makeSection({
        records: [borrowerParty([{ field_key: "borrower_cell_phone", value: "6145559999" }])],
      }),
    });

    renderTab();
    await act(async () => {
      await Promise.resolve();
    });

    const cellPhoneLabel = screen.getByText("Cell phone");
    const row = cellPhoneLabel.closest("div")?.parentElement as HTMLElement;
    fireEvent.click(within(row).getByRole("button", { name: "Edit" }));
    const input = screen.getByLabelText("Cell phone");
    fireEvent.change(input, { target: { value: "6145559999" } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    await act(async () => {
      await Promise.resolve();
    });

    expect(putMock).toHaveBeenCalledWith(
      expect.stringContaining("/fields/{field_key}"),
      expect.objectContaining({
        params: { path: { application_id: APPLICATION_ID, field_key: "borrower_cell_phone" } },
        body: { value: "6145559999" },
      }),
    );
    expect(await screen.findByText("6145559999")).toBeInTheDocument();
  });

  it("shows the returned message when a home_phone save 422s", async () => {
    mockGetSection(makeSection({ records: [borrowerParty()] }));
    putMock.mockResolvedValue({
      error: {
        detail: [
          {
            loc: ["body", "home_phone"],
            msg: "Home phone: cannot be empty while a cell phone is on file",
            type: "value_error",
          },
        ],
      },
    });

    renderTab();
    await act(async () => {
      await Promise.resolve();
    });

    const homePhoneLabel = screen.getByText("Home phone");
    const row = homePhoneLabel.closest("div")?.parentElement as HTMLElement;
    fireEvent.click(within(row).getByRole("button", { name: "Edit" }));
    fireEvent.change(screen.getByLabelText("Home phone"), { target: { value: "" } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    expect(
      await screen.findByText("Home phone: cannot be empty while a cell phone is on file"),
    ).toBeInTheDocument();
  });

  it("shows the No co-applicant panel when there is no co-borrower, and lets you add one", async () => {
    const borrower = borrowerParty();
    mockGetSection(makeSection({ records: [borrower] }));
    postMock.mockResolvedValue({
      data: makeSection({
        records: [
          borrower,
          {
            kind: "party",
            id: "party-co-1",
            role: "co_borrower",
            manual: true,
            fields: [
              field({ field_key: "co_borrower_first_name", label: "First name", value: "Marcus" }),
              field({ field_key: "co_borrower_last_name", label: "Last name", value: "Hale" }),
            ],
          },
        ],
      }),
      response: { status: 201 },
    });

    const { container } = renderTab();
    await act(async () => {
      await Promise.resolve();
    });

    expect(screen.getByText("No co-borrower yet")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Add co-borrower" }));
    const form = container.querySelector("form") as HTMLFormElement;
    expect(form).toBeTruthy();
    fireEvent.change(within(form).getByLabelText("First name"), { target: { value: "Marcus" } });
    fireEvent.change(within(form).getByLabelText("Last name"), { target: { value: "Hale" } });
    fireEvent.click(within(form).getByRole("button", { name: "Add co-borrower" }));

    await act(async () => {
      await Promise.resolve();
    });

    expect(postMock).toHaveBeenCalledWith(
      expect.stringContaining("/parties"),
      expect.objectContaining({
        params: { path: { application_id: APPLICATION_ID } },
        body: expect.objectContaining({ first_name: "Marcus", last_name: "Hale" }),
      }),
    );
    expect(await screen.findByText("Co-borrower")).toBeInTheDocument();
    expect(screen.queryByText("No co-borrower yet")).not.toBeInTheDocument();
  });

  it("toggles no_co_applicant_check via the universal edit pattern", async () => {
    const borrower = borrowerParty();
    mockGetSection(makeSection({ records: [borrower] }));
    putMock.mockResolvedValue({
      data: makeSection({
        records: [borrowerParty([{ field_key: "borrower_no_co_applicant_check", value: true }])],
      }),
    });

    renderTab();
    await act(async () => {
      await Promise.resolve();
    });

    fireEvent.click(screen.getByLabelText("No co-applicant"));

    await act(async () => {
      await Promise.resolve();
    });

    expect(putMock).toHaveBeenCalledWith(
      expect.stringContaining("/fields/{field_key}"),
      expect.objectContaining({
        params: {
          path: { application_id: APPLICATION_ID, field_key: "borrower_no_co_applicant_check" },
        },
        body: { value: true },
      }),
    );
    await act(async () => {
      await Promise.resolve();
    });
    expect((screen.getByLabelText("No co-applicant") as HTMLInputElement).checked).toBe(true);
    expect(screen.queryByText("No co-borrower yet")).not.toBeInTheDocument();
  });
});
