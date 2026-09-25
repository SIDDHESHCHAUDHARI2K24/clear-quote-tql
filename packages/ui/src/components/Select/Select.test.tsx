import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { Select } from "./Select";

const OPTIONS = [
  { value: "lo", label: "Loan Officer" },
  { value: "manager", label: "Manager" },
];

describe("Select", () => {
  it("is labelled and reports the chosen value", async () => {
    const onChange = vi.fn();
    render(<Select label="Role" options={OPTIONS} value="lo" onChange={onChange} />);

    const select = screen.getByLabelText("Role");
    expect(select).toHaveValue("lo");
    await userEvent.selectOptions(select, "manager");
    expect(onChange).toHaveBeenCalledWith("manager");
  });

  it("renders a placeholder option with an empty value", () => {
    render(
      <Select label="Role" options={OPTIONS} value="" onChange={vi.fn()} placeholder="Any role" />,
    );
    expect(screen.getByRole("option", { name: "Any role" })).toHaveValue("");
    expect(screen.getByLabelText("Role")).toHaveValue("");
  });

  it("links the error text via aria-describedby and marks the field invalid", () => {
    render(
      <Select
        label="Role"
        options={OPTIONS}
        value=""
        onChange={vi.fn()}
        placeholder="Choose"
        error="Pick a role"
      />,
    );
    const select = screen.getByLabelText("Role");
    expect(select).toHaveAttribute("aria-invalid", "true");
    expect(select).toHaveAccessibleDescription("Pick a role");
  });
});
