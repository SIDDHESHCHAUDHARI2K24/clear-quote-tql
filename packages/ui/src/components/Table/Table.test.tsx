import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { Table } from "./Table";
import type { TableColumn } from "./Table";

interface Row {
  id: string;
  name: string;
  amount: number;
}

const columns: TableColumn<Row>[] = [
  { key: "name", header: "Name" },
  { key: "amount", header: "Amount", align: "right", render: (row) => `$${row.amount}` },
];

const rows: Row[] = [
  { id: "1", name: "Alice", amount: 100 },
  { id: "2", name: "Bob", amount: 200 },
];

describe("Table", () => {
  it("renders headers and rows", () => {
    render(<Table columns={columns} rows={rows} rowKey={(r) => r.id} />);
    expect(screen.getByText("Name")).toBeInTheDocument();
    expect(screen.getByText("Alice")).toBeInTheDocument();
    expect(screen.getByText("$200")).toBeInTheDocument();
  });

  it("renders the empty state when there are no rows", () => {
    render(<Table columns={columns} rows={[]} rowKey={(r) => r.id} emptyState="Nothing yet" />);
    expect(screen.getByText("Nothing yet")).toBeInTheDocument();
  });

  it("calls onRowClick with the clicked row", async () => {
    const onRowClick = vi.fn();
    render(<Table columns={columns} rows={rows} rowKey={(r) => r.id} onRowClick={onRowClick} />);
    await userEvent.click(screen.getByText("Alice"));
    expect(onRowClick).toHaveBeenCalledWith(rows[0]);
  });
});
