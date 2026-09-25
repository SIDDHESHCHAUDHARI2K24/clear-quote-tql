import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import type { ApplicationListRow } from "../types";
import { ApplicationsTable } from "./ApplicationsTable";

const ROWS: ApplicationListRow[] = [
  {
    id: "1",
    client_name: "Aisha Coleman",
    property_label: "450 W Broad St, Columbus, OH",
    strategy: "ltr",
    purchase_price: "310000.00",
    status: "needs_attention",
    flag_count: 1,
    lo_id: "lo-1",
    lo_name: "Jordan Lee",
    updated_at: "2026-09-20T12:00:00Z",
  },
];

describe("ApplicationsTable", () => {
  it("shows an empty state with no rows", () => {
    render(
      <ApplicationsTable
        rows={[]}
        sort="-updated_at"
        onSortChange={vi.fn()}
        onRowClick={vi.fn()}
      />,
    );
    expect(screen.getByText("No applications match these filters")).toBeInTheDocument();
  });

  it("renders a row per application and calls onRowClick", async () => {
    const onRowClick = vi.fn();
    render(
      <ApplicationsTable
        rows={ROWS}
        sort="-updated_at"
        onSortChange={vi.fn()}
        onRowClick={onRowClick}
      />,
    );
    await userEvent.click(screen.getByText("Aisha Coleman"));
    expect(onRowClick).toHaveBeenCalledWith(ROWS[0]);
  });

  it("toggles the amount sort direction on click", async () => {
    const onSortChange = vi.fn();
    render(
      <ApplicationsTable
        rows={ROWS}
        sort="amount"
        onSortChange={onSortChange}
        onRowClick={vi.fn()}
      />,
    );
    await userEvent.click(screen.getByRole("button", { name: /Purchase price/ }));
    expect(onSortChange).toHaveBeenCalledWith("-amount");
  });

  it("marks the active sort column with aria-sort", () => {
    render(
      <ApplicationsTable
        rows={ROWS}
        sort="-updated_at"
        onSortChange={vi.fn()}
        onRowClick={vi.fn()}
      />,
    );
    const header = screen.getByRole("columnheader", { name: "Updated" });
    expect(header).toHaveAttribute("aria-sort", "descending");
  });
});
