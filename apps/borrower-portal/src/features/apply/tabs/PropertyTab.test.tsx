import { useState } from "react";

import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { MetrosOut } from "../api";
import { setPath } from "../paths";
import type { JsonRecord } from "../paths";
import { PropertyTab } from "./PropertyTab";

const METROS: MetrosOut = {
  states: [
    { state: "FL", metros: ["Tampa", "Davenport"] },
    { state: "TX", metros: ["Austin"] },
  ],
};

function Harness({
  initial = {},
  errors = {},
}: {
  initial?: JsonRecord;
  errors?: Record<string, string>;
}) {
  const [data, setData] = useState<JsonRecord>(initial);
  return (
    <PropertyTab
      data={data}
      set={(path, value) => setData((prev) => setPath(prev, path, value))}
      errorFor={(path) => errors[path]}
      disabled={false}
      metros={METROS}
    />
  );
}

describe("PropertyTab (CQ-032 spec.md tab 2)", () => {
  it("shows an address form when the borrower has a property in mind", () => {
    render(<Harness initial={{ has_property: true }} />);
    expect(screen.getByLabelText("Street address")).toBeInTheDocument();
    expect(screen.queryByText("States")).not.toBeInTheDocument();
  });

  it("shows the two-tier states/metros picker when there is no property yet", () => {
    render(<Harness initial={{ has_property: false }} />);
    expect(screen.queryByLabelText("Street address")).not.toBeInTheDocument();
    expect(screen.getByText("States")).toBeInTheDocument();
    expect(screen.getByText("Metros")).toBeInTheDocument();
  });

  it("scopes the metro options to the selected states", () => {
    render(<Harness initial={{ has_property: false, buy_box_states: ["FL"] }} />);
    const metroTrigger = screen.getByRole("button", { name: /^Metros/ });
    fireEvent.click(metroTrigger);
    const popover = screen.getByRole("group");
    expect(within(popover).getByText("Tampa, FL")).toBeInTheDocument();
    expect(within(popover).queryByText("Austin, TX")).not.toBeInTheDocument();
  });

  it("offers primary-occupancy down payment options for a primary residence", () => {
    render(<Harness initial={{ occupancy: "primary" }} />);
    const select = screen.getByLabelText("Down payment") as HTMLSelectElement;
    const values = Array.from(select.options).map((o) => o.value);
    expect(values).toEqual(expect.arrayContaining(["0.03", "0.05", "0.10", "0.15", "0.20"]));
  });

  it("offers investment-occupancy down payment options for an STR", () => {
    render(<Harness initial={{ occupancy: "str" }} />);
    const select = screen.getByLabelText("Down payment") as HTMLSelectElement;
    const values = Array.from(select.options).map((o) => o.value);
    expect(values).toEqual(expect.arrayContaining(["0.15", "0.20", "0.25"]));
    expect(values).not.toContain("0.03");
  });

  it("shows the metro-required error linked to the picker", () => {
    render(
      <Harness
        initial={{ has_property: false }}
        errors={{ buy_box_metros: "Choose at least one metro." }}
      />,
    );
    expect(screen.getByText("Choose at least one metro.")).toBeInTheDocument();
  });
});
