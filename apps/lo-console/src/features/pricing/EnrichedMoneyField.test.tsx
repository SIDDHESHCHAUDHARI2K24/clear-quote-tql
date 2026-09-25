// PR review round (fresh stage-6): same no-edit-no-override rule as
// `EnrichedPercentField`, applied here for consistency (`MoneyInput` never
// round-trips `value` through a unit conversion, so this field wasn't
// actually vulnerable to the CRITICAL round-trip bug, but a touched/dirty
// flag keeps both enriched fields' blur behaviour identical).
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { EnrichedMoneyField } from "./EnrichedMoneyField";
import type { PricingField } from "./api";

function field(value: string): PricingField {
  return {
    field_key: "homeowners_ins_annual",
    value,
    source: "steadily",
    source_ref: null,
    overridden: false,
    original_value: null,
  };
}

describe("EnrichedMoneyField -- no-edit-no-override (CQ-017 review)", () => {
  it("focus then blur with no typing does not call onOverride", async () => {
    const onOverride = vi.fn();
    const onRevert = vi.fn();
    render(
      <EnrichedMoneyField
        label="Homeowners insurance (annual)"
        ariaLabel="Homeowners insurance"
        field={field("1800.00")}
        onOverride={onOverride}
        onRevert={onRevert}
      />,
    );

    const input = screen.getByLabelText("Homeowners insurance");
    await userEvent.click(input);
    await userEvent.tab();

    expect(onOverride).not.toHaveBeenCalled();
  });

  it("typing a new value still overrides it correctly", async () => {
    const onOverride = vi.fn();
    const onRevert = vi.fn();
    render(
      <EnrichedMoneyField
        label="Homeowners insurance (annual)"
        ariaLabel="Homeowners insurance"
        field={field("1800.00")}
        onOverride={onOverride}
        onRevert={onRevert}
      />,
    );

    const input = screen.getByLabelText("Homeowners insurance");
    await userEvent.clear(input);
    await userEvent.type(input, "2200.00");
    await userEvent.tab();

    expect(onOverride).toHaveBeenCalledTimes(1);
    expect(onOverride).toHaveBeenCalledWith("2200.00");
  });
});
