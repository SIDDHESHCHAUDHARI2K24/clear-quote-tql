import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { LoFilter } from "./LoFilter";

const LOS = [
  { id: "lo-1", full_name: "Jordan Lee" },
  { id: "lo-2", full_name: "Riley Admin" },
];

describe("LoFilter", () => {
  it("lists every LO plus an 'all' placeholder, and calls onChange with the picked id", async () => {
    const onChange = vi.fn();
    render(<LoFilter los={LOS} value={null} onChange={onChange} />);

    const select = screen.getByLabelText("Loan officer");
    expect(select).toHaveValue("");

    await userEvent.selectOptions(select, "Jordan Lee");
    expect(onChange).toHaveBeenCalledWith("lo-1");
  });

  it("calls onChange with null when 'All loan officers' is picked", async () => {
    const onChange = vi.fn();
    render(<LoFilter los={LOS} value="lo-1" onChange={onChange} />);

    const select = screen.getByLabelText("Loan officer");
    await userEvent.selectOptions(select, "All loan officers");
    expect(onChange).toHaveBeenCalledWith(null);
  });
});
