import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import type { ApplicationListRow } from "../types";
import { ApplicationRow } from "./ApplicationRow";

const ROW: ApplicationListRow = {
  id: "11111111-1111-1111-1111-111111111111",
  client_name: "Aisha Coleman",
  property_label: "450 W Broad St, Columbus, OH",
  strategy: "ltr",
  purchase_price: "310000.00",
  status: "needs_attention",
  flag_count: 1,
  lo_id: "22222222-2222-2222-2222-222222222222",
  lo_name: "Jordan Lee",
  updated_at: "2026-09-20T12:00:00Z",
};

function renderRow(row: ApplicationListRow = ROW, onClick?: (row: ApplicationListRow) => void) {
  return render(
    <table>
      <tbody>
        <ApplicationRow row={row} onClick={onClick} />
      </tbody>
    </table>,
  );
}

describe("ApplicationRow", () => {
  it("renders every spec.md field", () => {
    renderRow();
    expect(screen.getByText("Aisha Coleman")).toBeInTheDocument();
    expect(screen.getByText("450 W Broad St, Columbus, OH")).toBeInTheDocument();
    expect(screen.getByText("LTR")).toBeInTheDocument();
    expect(screen.getByText("$310,000")).toBeInTheDocument();
    expect(screen.getByText("Needs attention")).toBeInTheDocument();
    expect(screen.getByText("Jordan Lee")).toBeInTheDocument();
    expect(screen.getByLabelText("1 open flag")).toBeInTheDocument();
  });

  it("shows no flag badge when flag_count is 0", () => {
    renderRow({ ...ROW, flag_count: 0 });
    expect(screen.queryByLabelText(/open flag/)).not.toBeInTheDocument();
  });

  it("shows a dash property label when null", () => {
    renderRow({ ...ROW, property_label: null });
    expect(screen.getByRole("row")).toHaveTextContent("—");
  });

  it("calls onClick with the row on click, and on Enter", async () => {
    const onClick = vi.fn();
    renderRow(ROW, onClick);
    const row = screen.getByRole("button");
    await userEvent.click(row);
    expect(onClick).toHaveBeenCalledWith(ROW);

    onClick.mockClear();
    row.focus();
    await userEvent.keyboard("{Enter}");
    expect(onClick).toHaveBeenCalledWith(ROW);
  });

  it("is not interactive without onClick", () => {
    renderRow(ROW);
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });
});
