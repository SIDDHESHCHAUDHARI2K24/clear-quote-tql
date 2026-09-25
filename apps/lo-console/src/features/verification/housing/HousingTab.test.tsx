import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
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
import { HousingTab } from "./HousingTab";

// docs/backlog/CQ-028-verification-tabs/spec.md AC2: "adding a prior address
// that brings history to >= 24 months clears the housing flag; a shorter
// one keeps it with the months shown."

const APPLICATION_ID = "11111111-1111-1111-1111-111111111111";
const SUMMARY = makeSummary();

const FIELD_LABELS: Record<string, string> = {
  street_address: "Street address",
  city: "City",
  state: "State",
  zip: "Zip",
  housing_status: "Own / rent",
  residence_years: "Years at address",
  residence_months: "Months at address",
  vom_completed: "VOM completed",
};

function housingField(
  rowId: string,
  suffix: keyof typeof FIELD_LABELS,
  value: SectionField["value"],
  overrides: Partial<SectionField> = {},
): SectionField {
  return {
    field_key: `housing_history.${rowId}.${suffix}`,
    label: FIELD_LABELS[suffix],
    value,
    source: "encompass",
    overridden: false,
    editable: true,
    ...overrides,
  };
}

function makeHousingRecord(
  rowId: string,
  values: Partial<Record<keyof typeof FIELD_LABELS, SectionField["value"]>>,
  manual = false,
): SectionRecord {
  const defaults: Record<keyof typeof FIELD_LABELS, SectionField["value"]> = {
    street_address: "123 Main St",
    city: "Austin",
    state: "TX",
    zip: "78701",
    housing_status: "rent",
    residence_years: 1,
    residence_months: 8,
    vom_completed: false,
  };
  const merged = { ...defaults, ...values };
  return {
    kind: "housing_history",
    id: rowId,
    role: null,
    manual,
    fields: (Object.keys(defaults) as Array<keyof typeof FIELD_LABELS>).map((suffix) =>
      housingField(rowId, suffix, merged[suffix] ?? null),
    ),
  };
}

function mockGet(section: SectionResponse) {
  getMock.mockImplementation((path: string) =>
    Promise.resolve({ data: path.includes("/summary") ? SUMMARY : section }),
  );
}

function renderTab() {
  return render(
    <ToastProvider>
      <WorkspaceProvider applicationId={APPLICATION_ID}>
        <HousingTab applicationId={APPLICATION_ID} />
      </WorkspaceProvider>
    </ToastProvider>,
  );
}

describe("HousingTab (docs/backlog/CQ-028-verification-tabs/spec.md AC2)", () => {
  afterEach(() => {
    getMock.mockReset();
    putMock.mockReset();
    postMock.mockReset();
  });

  it("shows the shortfall and does not claim the requirement is met at 20 months", async () => {
    const section = makeSection({
      tab: "housing",
      records: [makeHousingRecord("row-1", {})],
      housing: { total_months: 20, required_months: 24, meets_requirement: false },
      flags: [
        {
          id: "flag-1",
          tab: "housing",
          field_key: "housing_history.row-1.residence_years",
          rule: "housing_history_min_months",
          severity: "warning",
          message: "Housing history is 4 months short of the 24-month requirement.",
        },
      ],
    });
    mockGet(section);

    renderTab();
    await act(async () => {
      await Promise.resolve();
    });

    expect(screen.getByText(/Housing history: 20 \/ 24 months/)).toBeInTheDocument();
    expect(screen.getByText(/below the 24-month requirement/)).toBeInTheDocument();
    expect(screen.queryByText(/requirement met/)).not.toBeInTheDocument();
    // Rendered both by FlagList (top-of-tab summary) and inline by FieldRow
    // against the flagged field.
    expect(
      screen.getAllByText("Housing history is 4 months short of the 24-month requirement."),
    ).toHaveLength(2);
  });

  it("shows the requirement met and no flag at 24+ months", async () => {
    const section = makeSection({
      tab: "housing",
      records: [makeHousingRecord("row-1", { residence_years: 2, residence_months: 0 })],
      housing: { total_months: 24, required_months: 24, meets_requirement: true },
      flags: [],
    });
    mockGet(section);

    renderTab();
    await act(async () => {
      await Promise.resolve();
    });

    expect(screen.getByText(/Housing history: 24 \/ 24 months/)).toBeInTheDocument();
    expect(screen.getByText(/requirement met/)).toBeInTheDocument();
  });

  it('"Add prior address" submits the form and calls addHousing with the right body', async () => {
    const initialSection = makeSection({
      tab: "housing",
      records: [makeHousingRecord("row-1", {})],
      housing: { total_months: 20, required_months: 24, meets_requirement: false },
      flags: [],
    });
    mockGet(initialSection);

    const updatedSection = makeSection({
      tab: "housing",
      records: [
        makeHousingRecord("row-1", {}),
        makeHousingRecord("row-2", { street_address: "456 Prior Ave" }),
      ],
      housing: { total_months: 32, required_months: 24, meets_requirement: true },
      flags: [],
    });
    postMock.mockResolvedValue({ data: updatedSection });

    renderTab();
    await act(async () => {
      await Promise.resolve();
    });

    fireEvent.click(screen.getByText("Add prior address"));

    fireEvent.change(screen.getByLabelText("Street address"), {
      target: { value: "456 Prior Ave" },
    });
    fireEvent.change(screen.getByLabelText("City"), { target: { value: "Dallas" } });
    fireEvent.change(screen.getByLabelText("State"), { target: { value: "TX" } });
    fireEvent.change(screen.getByLabelText("Zip"), { target: { value: "75201" } });
    fireEvent.change(screen.getByLabelText("Own / rent"), { target: { value: "own" } });
    fireEvent.change(screen.getByLabelText("Years at address"), { target: { value: "2" } });
    fireEvent.change(screen.getByLabelText("Months at address"), { target: { value: "0" } });

    await act(async () => {
      fireEvent.click(screen.getByText("Save"));
      await Promise.resolve();
    });

    expect(postMock).toHaveBeenCalledWith(
      "/api/v1/applications/{application_id}/housing_history",
      expect.objectContaining({
        params: { path: { application_id: APPLICATION_ID } },
        body: expect.objectContaining({
          street_address: "456 Prior Ave",
          city: "Dallas",
          state: "TX",
          zip: "75201",
          housing_status: "own",
          residence_years: 2,
          residence_months: 0,
        }),
      }),
    );

    // Form closes back to the "Add prior address" trigger, and the new row
    // (from the applied response) renders.
    await waitFor(() => {
      expect(screen.getByText("Add prior address")).toBeInTheDocument();
    });
    expect(screen.getByText(/Housing history: 32 \/ 24 months/)).toBeInTheDocument();
  });

  it("surfaces a returned error message when a field edit fails", async () => {
    const section = makeSection({
      tab: "housing",
      records: [makeHousingRecord("row-1", {})],
      housing: { total_months: 20, required_months: 24, meets_requirement: false },
      flags: [],
    });
    mockGet(section);
    putMock.mockResolvedValue({
      data: undefined,
      error: { error: { message: "Zip must be 5 digits." } },
    });

    renderTab();
    await act(async () => {
      await Promise.resolve();
    });

    const editButtons = screen.getAllByText("Edit");
    // Street address is the first field row rendered.
    fireEvent.click(editButtons[0]);
    fireEvent.change(screen.getByLabelText("Street address"), {
      target: { value: "" },
    });

    await act(async () => {
      fireEvent.click(screen.getByText("Save"));
      await Promise.resolve();
    });

    expect(await screen.findByText("Zip must be 5 digits.")).toBeInTheDocument();
  });
});
