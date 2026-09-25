import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import type { ClientRow } from "../types";
import { ClientsTable } from "./ClientsTable";

const ROWS: ClientRow[] = [
  {
    id: "1",
    name: "Marcus Hale",
    email: "marcus.hale@clearquote-demo.test",
    phone: "555-0100",
    lo_id: "lo-1",
    lo_name: "Jordan Lee",
    application_count: 2,
    active_status: "priced",
    last_activity: "2026-09-20T12:00:00Z",
  },
];

describe("ClientsTable", () => {
  it("shows an empty state with no rows", () => {
    render(
      <ClientsTable rows={[]} sort="-last_activity" onSortChange={vi.fn()} onRowClick={vi.fn()} />,
    );
    expect(screen.getByText("No clients match these filters")).toBeInTheDocument();
  });

  it("renders a row per client and calls onRowClick", async () => {
    const onRowClick = vi.fn();
    render(
      <ClientsTable
        rows={ROWS}
        sort="-last_activity"
        onSortChange={vi.fn()}
        onRowClick={onRowClick}
      />,
    );
    expect(screen.getByText("Marcus Hale")).toBeInTheDocument();
    expect(screen.getByText("marcus.hale@clearquote-demo.test")).toBeInTheDocument();
    await userEvent.click(screen.getByText("Marcus Hale"));
    expect(onRowClick).toHaveBeenCalledWith(ROWS[0]);
  });

  it("shows a dash when there's no active application", () => {
    const row: ClientRow = { ...ROWS[0], active_status: null };
    render(
      <ClientsTable
        rows={[row]}
        sort="-last_activity"
        onSortChange={vi.fn()}
        onRowClick={vi.fn()}
      />,
    );
    expect(screen.getAllByText("—").length).toBeGreaterThan(0);
  });

  it("sorts by name on header click", async () => {
    const onSortChange = vi.fn();
    render(
      <ClientsTable
        rows={ROWS}
        sort="-last_activity"
        onSortChange={onSortChange}
        onRowClick={vi.fn()}
      />,
    );
    await userEvent.click(screen.getByRole("button", { name: "Name" }));
    expect(onSortChange).toHaveBeenCalledWith("name");
  });

  it("marks each active sort column with its own fixed direction", () => {
    // `name` is always ascending, `-last_activity` always descending --
    // `aria-sort` must reflect each column's own direction, not whichever
    // one happens to be active (code review regression check).
    const { rerender } = render(
      <ClientsTable rows={ROWS} sort="name" onSortChange={vi.fn()} onRowClick={vi.fn()} />,
    );
    expect(screen.getByRole("columnheader", { name: "Name" })).toHaveAttribute(
      "aria-sort",
      "ascending",
    );

    rerender(
      <ClientsTable
        rows={ROWS}
        sort="-last_activity"
        onSortChange={vi.fn()}
        onRowClick={vi.fn()}
      />,
    );
    expect(screen.getByRole("columnheader", { name: "Last activity" })).toHaveAttribute(
      "aria-sort",
      "descending",
    );
    expect(screen.getByRole("columnheader", { name: "Name" })).toHaveAttribute("aria-sort", "none");
  });
});
