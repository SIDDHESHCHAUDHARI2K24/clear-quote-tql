import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const { getMock, patchMock, putMock, deleteMock } = vi.hoisted(() => ({
  getMock: vi.fn(),
  patchMock: vi.fn(),
  putMock: vi.fn(),
  deleteMock: vi.fn(),
}));

vi.mock("@cq/api-client", () => ({
  createApiClient: () => ({
    GET: getMock,
    PUT: putMock,
    POST: vi.fn(),
    PATCH: patchMock,
    DELETE: deleteMock,
  }),
}));

import { ToastProvider } from "@cq/ui";

import { makeSummary } from "../../workspace/test-fixtures";
import { WorkspaceProvider } from "../../workspace";
import { makeSection } from "../shared/test-fixtures";
import { PropertyTab } from "./PropertyTab";
import type { SectionResponse } from "../shared";

const APPLICATION_ID = "11111111-1111-1111-1111-111111111111";
const SUMMARY = makeSummary();

function loanRecord(occupancy: "primary" | "investment") {
  return {
    kind: "loan" as const,
    id: APPLICATION_ID,
    manual: false,
    fields: [
      {
        field_key: "occupancy_type",
        label: "Occupancy",
        value: occupancy,
        source: "encompass" as const,
        overridden: false,
        editable: true,
      },
      {
        field_key: "investment_strategy",
        label: "Investment strategy",
        value: occupancy === "investment" ? "ltr" : null,
        source: "encompass" as const,
        overridden: false,
        editable: true,
      },
    ],
  };
}

function propertyRecord(overrides: { tbd?: boolean } = {}) {
  return {
    kind: "property" as const,
    id: "prop-1",
    manual: false,
    fields: [
      {
        field_key: "property.street_address",
        label: "Street address",
        value: overrides.tbd ? null : "450 W Broad St",
        source: "encompass" as const,
        overridden: false,
        editable: false,
      },
      {
        field_key: "property.city",
        label: "City",
        value: "Davenport",
        source: "encompass" as const,
        overridden: false,
        editable: false,
      },
      {
        field_key: "property.state",
        label: "State",
        value: "FL",
        source: "encompass" as const,
        overridden: false,
        editable: false,
      },
      {
        field_key: "property.zip",
        label: "Zip",
        value: "33896",
        source: "encompass" as const,
        overridden: false,
        editable: false,
      },
      {
        field_key: "property.county",
        label: "County",
        value: "Polk",
        source: "property_search" as const,
        overridden: false,
        editable: false,
      },
      {
        field_key: "property.property_type",
        label: "Property type",
        value: "single_family",
        source: "encompass" as const,
        overridden: false,
        editable: false,
      },
      {
        field_key: "property.number_of_units",
        label: "Units",
        value: 1,
        source: "encompass" as const,
        overridden: false,
        editable: false,
      },
    ],
  };
}

function makePropertySection(overrides: Partial<SectionResponse> = {}, tbd = false) {
  return makeSection({
    tab: "property",
    records: [propertyRecord({ tbd }), loanRecord("investment")],
    property: {
      tbd,
      recommend_matches: tbd,
      buy_box_states: [],
      buy_box_metros: [],
    },
    ...overrides,
  });
}

async function renderReady(section: SectionResponse) {
  getMock.mockImplementation((path: string) =>
    Promise.resolve({ data: path.includes("/summary") ? SUMMARY : section }),
  );
  render(
    <ToastProvider>
      <WorkspaceProvider applicationId={APPLICATION_ID}>
        <PropertyTab applicationId={APPLICATION_ID} />
      </WorkspaceProvider>
    </ToastProvider>,
  );
  await act(async () => {
    await Promise.resolve();
  });
}

describe("PropertyTab (docs/backlog/CQ-028-verification-tabs/spec.md Tab 5)", () => {
  afterEach(() => {
    getMock.mockReset();
    patchMock.mockReset();
    putMock.mockReset();
    deleteMock.mockReset();
  });

  it("shows the TBD label and an 'Enter address' action when the property has no specific address (plan.md #30)", async () => {
    await renderReady(makePropertySection({}, true));
    expect(screen.getByTestId("property-tbd-label")).toHaveTextContent("TBD");
    expect(screen.getByRole("button", { name: "Enter address" })).toBeInTheDocument();
  });

  it("AC6: entering an address turns TBD off and removes the TBD label", async () => {
    await renderReady(makePropertySection({}, true));
    patchMock.mockResolvedValueOnce({
      data: makePropertySection({}, false),
    });

    fireEvent.click(screen.getByRole("button", { name: "Enter address" }));
    fireEvent.change(screen.getByLabelText("Street address"), {
      target: { value: "450 W Broad St" },
    });
    fireEvent.change(screen.getByLabelText("City"), { target: { value: "Davenport" } });
    fireEvent.change(screen.getByLabelText("Zip"), { target: { value: "33896" } });
    fireEvent.click(screen.getByRole("button", { name: "Save address" }));

    await waitFor(() => expect(patchMock).toHaveBeenCalledTimes(1));
    const [, options] = patchMock.mock.calls[0];
    expect(options.body.address).toMatchObject({
      street_address: "450 W Broad St",
      city: "Davenport",
    });

    await waitFor(() => expect(screen.queryByTestId("property-tbd-label")).not.toBeInTheDocument());
  });

  it("AC6: picking states then metros stores both via PATCH /property", async () => {
    await renderReady(makePropertySection({}, false));

    const withState = makePropertySection(
      {
        property: {
          tbd: false,
          recommend_matches: false,
          buy_box_states: ["FL"],
          buy_box_metros: [],
        },
      },
      false,
    );
    patchMock.mockResolvedValueOnce({ data: withState });
    getMock.mockImplementation((path: string) => {
      if (path.includes("/summary")) return Promise.resolve({ data: SUMMARY });
      if (path.includes("/reference/metros"))
        return Promise.resolve({
          data: { states: [{ state: "FL", metros: ["Tampa", "Orlando"] }] },
        });
      return Promise.resolve({ data: withState });
    });

    // MultiSelect's trigger has no unique accessible name here (the Metros
    // trigger's disabled placeholder, "Pick states first", itself contains
    // the substring "states") -- `aria-expanded` picks out just the two
    // MultiSelect triggers, in document order: States first, then Metros.
    const multiSelectTriggers = () =>
      screen.getAllByRole("button").filter((button) => button.hasAttribute("aria-expanded"));

    fireEvent.click(multiSelectTriggers()[0]);
    fireEvent.click(screen.getByLabelText("Florida"));

    await waitFor(() => expect(patchMock).toHaveBeenCalledTimes(1));
    expect(patchMock.mock.calls[0][1].body).toEqual({ buy_box_states: ["FL"] });

    await waitFor(() => expect(multiSelectTriggers()[1]).not.toBeDisabled());

    const withTampaOnly = makePropertySection(
      {
        property: {
          tbd: false,
          recommend_matches: false,
          buy_box_states: ["FL"],
          buy_box_metros: ["Tampa"],
        },
      },
      false,
    );
    patchMock.mockResolvedValueOnce({ data: withTampaOnly });

    // Clicking a checkbox does not close the popover, so both selections
    // happen in one open/close cycle; MultiSelect computes the new value
    // set from its current `value` prop each click, so the second click
    // (Orlando) already sees Tampa in `property.buy_box_metros` from the
    // re-render `applyResult` triggered after the first PATCH resolved.
    fireEvent.click(multiSelectTriggers()[1]);
    fireEvent.click(screen.getByLabelText("Tampa (FL)"));
    await waitFor(() => expect(patchMock).toHaveBeenCalledTimes(2));

    const withBothMetros = makePropertySection(
      {
        property: {
          tbd: false,
          recommend_matches: false,
          buy_box_states: ["FL"],
          buy_box_metros: ["Tampa", "Orlando"],
        },
      },
      false,
    );
    patchMock.mockResolvedValueOnce({ data: withBothMetros });
    fireEvent.click(screen.getByLabelText("Orlando (FL)"));

    await waitFor(() => expect(patchMock).toHaveBeenCalledTimes(3));
    expect(patchMock.mock.calls[2][1].body.buy_box_metros).toEqual(
      expect.arrayContaining(["Tampa", "Orlando"]),
    );
  });

  it("renders occupancy on the Property tab's Loan card, editable via the universal field pattern", async () => {
    await renderReady(makePropertySection({}, false));
    expect(screen.getByText("Occupancy")).toBeInTheDocument();
    expect(screen.getByText("Investment")).toBeInTheDocument(); // the field's current value

    // Occupancy is the first field in the Loan card (fields.py's
    // APPLICATION_FIELDS order: occupancy_type, investment_strategy).
    putMock.mockResolvedValueOnce({ data: makePropertySection({}, false) });
    fireEvent.click(screen.getAllByRole("button", { name: "Edit" })[0]);
    expect(screen.getByLabelText("Occupancy")).toBeInTheDocument();
  });
});
