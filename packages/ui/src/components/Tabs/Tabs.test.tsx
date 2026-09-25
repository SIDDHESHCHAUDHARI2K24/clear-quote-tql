import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { Tabs } from "./Tabs";
import type { TabItem } from "./Tabs";

const items: TabItem[] = [
  { id: "borrowers", label: "Borrowers", status: "complete" },
  { id: "housing", label: "Housing", status: "flagged", flagCount: 2 },
  { id: "credit", label: "Credit", status: "pending" },
  { id: "closed", label: "Closed tab", disabled: true },
];

describe("Tabs", () => {
  it("renders all tabs with the active one marked selected", () => {
    render(<Tabs items={items} activeId="housing" onChange={vi.fn()} />);
    expect(screen.getByRole("tab", { name: /housing/i })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("tab", { name: /borrowers/i })).toHaveAttribute(
      "aria-selected",
      "false",
    );
  });

  it("shows a flag count badge for flagged tabs", () => {
    render(<Tabs items={items} activeId="borrowers" onChange={vi.fn()} />);
    expect(screen.getByLabelText("2 flags")).toBeInTheDocument();
  });

  it("calls onChange when a tab is clicked, but not for disabled tabs", async () => {
    const onChange = vi.fn();
    render(<Tabs items={items} activeId="borrowers" onChange={onChange} />);
    await userEvent.click(screen.getByRole("tab", { name: /credit/i }));
    expect(onChange).toHaveBeenCalledWith("credit");

    await userEvent.click(screen.getByRole("tab", { name: /closed tab/i }));
    expect(onChange).toHaveBeenCalledTimes(1);
  });
});
