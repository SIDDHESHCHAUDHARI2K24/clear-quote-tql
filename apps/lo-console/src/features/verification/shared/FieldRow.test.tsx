import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { FieldRow } from "./FieldRow";
import type { SectionField, SectionFlag } from "./api";

function makeField(overrides: Partial<SectionField> = {}): SectionField {
  return {
    field_key: "borrower_cell_phone",
    label: "Cell phone",
    value: "6145557007",
    source: "encompass",
    overridden: false,
    editable: true,
    ...overrides,
  };
}

function makeFlag(overrides: Partial<SectionFlag> = {}): SectionFlag {
  return {
    id: "flag-1",
    tab: "borrowers",
    field_key: "borrower_cell_phone",
    rule: "phone_format",
    severity: "warning",
    message: "Cell phone looks invalid",
    ...overrides,
  };
}

describe("FieldRow", () => {
  it("shows the label, formatted value and source badge", () => {
    render(<FieldRow field={makeField()} onSave={vi.fn()} />);
    expect(screen.getByText("Cell phone")).toBeInTheDocument();
    expect(screen.getByText("6145557007")).toBeInTheDocument();
    expect(screen.getByText("Encompass")).toBeInTheDocument();
  });

  it("edits and saves a new value", async () => {
    const onSave = vi.fn().mockResolvedValue(undefined);
    render(<FieldRow field={makeField()} onSave={onSave} />);

    fireEvent.click(screen.getByRole("button", { name: "Edit" }));
    const input = screen.getByLabelText("Cell phone");
    fireEvent.change(input, { target: { value: "6145559999" } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    expect(onSave).toHaveBeenCalledWith("6145559999");
  });

  it("rejects a non-numeric 'number' draft instead of silently saving null (code-review fix: Number(\"abc\") is NaN, which JSON.stringify()s to null)", async () => {
    const onSave = vi.fn().mockResolvedValue(undefined);
    render(
      <FieldRow
        field={makeField({
          field_key: "co_borrower_dependents_count",
          label: "Dependents",
          value: 2,
        })}
        kind="number"
        onSave={onSave}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Edit" }));
    fireEvent.change(screen.getByLabelText("Dependents"), { target: { value: "abc" } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    expect(await screen.findByText("Enter a number.")).toBeInTheDocument();
    expect(onSave).not.toHaveBeenCalled();
    // Still editing -- the bad entry did not silently commit as null.
    expect(screen.getByRole("button", { name: "Save" })).toBeInTheDocument();
  });

  it("shows the revert action and calls onRevert when the field is overridden", () => {
    const onRevert = vi.fn().mockResolvedValue(undefined);
    render(
      <FieldRow
        field={makeField({ source: "lo_override", overridden: true, original_value: "old" })}
        onSave={vi.fn()}
        onRevert={onRevert}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Revert to source" }));
    expect(onRevert).toHaveBeenCalled();
  });

  it("highlights the matching flag's message inline (spec.md 'Shared pieces')", () => {
    render(<FieldRow field={makeField()} flag={makeFlag()} onSave={vi.fn()} />);
    expect(screen.getByText("Cell phone looks invalid")).toBeInTheDocument();
  });

  it("shows an error from a failed save without closing the editor", async () => {
    const onSave = vi.fn().mockRejectedValue(new Error("Home phone: cannot be empty"));
    render(
      <FieldRow
        field={makeField({ field_key: "borrower_home_phone", label: "Home phone" })}
        onSave={onSave}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Edit" }));
    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    expect(await screen.findByText("Home phone: cannot be empty")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Save" })).toBeInTheDocument();
  });

  it("hides Edit for a non-editable field (e.g. a property record's fields, edited via PATCH /property)", () => {
    render(<FieldRow field={makeField({ editable: false })} onSave={vi.fn()} />);
    expect(screen.queryByRole("button", { name: "Edit" })).not.toBeInTheDocument();
  });
});
