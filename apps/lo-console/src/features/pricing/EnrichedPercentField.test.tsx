// PR review round (fresh stage-6, CRITICAL): focusing and then blurring an
// enriched percent field with no edit must never call `onOverride`. The
// original `handleBlur` compared the round-tripped display value
// (`fractionToPercentInputValue` -> x100/.toFixed(3), then
// `percentInputValueToFraction` -> /100/.toFixed(4)) against `field.value`
// with a strict `!==`. Seeded rates like "0.000089" round-trip to
// "0.0001" -- a value that never matches "0.000089" -- so every LO who
// merely tabbed through the field silently overrode it, marked the
// application's quotes stale, and flipped the badge to "LO override".
//
// Fix: a touched/dirty flag set only in the input's own `onChange`, so
// blur never fires `onOverride` unless the user actually typed something.
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { EnrichedPercentField } from "./EnrichedPercentField";
import type { PricingField } from "./api";

function field(value: string): PricingField {
  return {
    field_key: "property_tax_annual_rate",
    value,
    source: "smartasset",
    source_ref: null,
    overridden: false,
    original_value: null,
  };
}

describe("EnrichedPercentField -- no-edit-no-override (CQ-017 review)", () => {
  it.each(["0.000089", "0.0064", "0.0153", "0.0225"])(
    "focus then blur with no typing does not call onOverride for %s",
    async (value) => {
      const onOverride = vi.fn();
      const onRevert = vi.fn();
      render(
        <EnrichedPercentField
          label="Property tax rate"
          ariaLabel="Property tax rate"
          field={field(value)}
          onOverride={onOverride}
          onRevert={onRevert}
        />,
      );

      const input = screen.getByLabelText("Property tax rate");
      await userEvent.click(input);
      await userEvent.tab();

      expect(onOverride).not.toHaveBeenCalled();
    },
  );

  it("typing a new value still overrides it correctly", async () => {
    const onOverride = vi.fn();
    const onRevert = vi.fn();
    render(
      <EnrichedPercentField
        label="Property tax rate"
        ariaLabel="Property tax rate"
        field={field("0.0064")}
        onOverride={onOverride}
        onRevert={onRevert}
      />,
    );

    const input = screen.getByLabelText("Property tax rate");
    await userEvent.clear(input);
    await userEvent.type(input, "1.250");
    await userEvent.tab();

    expect(onOverride).toHaveBeenCalledTimes(1);
    expect(onOverride).toHaveBeenCalledWith("0.012500");
  });

  it("typing a small edited value preserves precision instead of truncating to 4dp", async () => {
    const onOverride = vi.fn();
    const onRevert = vi.fn();
    render(
      <EnrichedPercentField
        label="Property tax rate"
        ariaLabel="Property tax rate"
        field={field("0.0064")}
        onOverride={onOverride}
        onRevert={onRevert}
      />,
    );

    const input = screen.getByLabelText("Property tax rate");
    await userEvent.clear(input);
    await userEvent.type(input, "0.0089");
    await userEvent.tab();

    // 0.0089% -> 0.000089 as a 0-1 fraction; the old 4dp fraction precision
    // would have rounded this to "0.0001", silently changing what the LO
    // typed.
    expect(onOverride).toHaveBeenCalledTimes(1);
    expect(onOverride).toHaveBeenCalledWith("0.000089");
  });

  it("typing then blurring back to the same displayed value does not override", async () => {
    const onOverride = vi.fn();
    const onRevert = vi.fn();
    render(
      <EnrichedPercentField
        label="Property tax rate"
        ariaLabel="Property tax rate"
        field={field("0.0064")}
        onOverride={onOverride}
        onRevert={onRevert}
      />,
    );

    const input = screen.getByLabelText("Property tax rate");
    await userEvent.click(input);
    await userEvent.type(input, "9");
    await userEvent.keyboard("{Backspace}");
    await userEvent.tab();

    expect(onOverride).not.toHaveBeenCalled();
  });
});
