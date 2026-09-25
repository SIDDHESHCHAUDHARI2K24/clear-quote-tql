import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { Pagination } from "./Pagination";

describe("Pagination", () => {
  it("shows the visible range and page count", () => {
    render(<Pagination page={2} pageSize={25} total={60} onChange={vi.fn()} />);
    expect(screen.getByRole("navigation", { name: "Pagination" })).toBeInTheDocument();
    expect(screen.getByText("Showing 26–50 of 60")).toBeInTheDocument();
    expect(screen.getByText("Page 2 of 3")).toBeInTheDocument();
  });

  it("calls onChange with the previous and next page", async () => {
    const onChange = vi.fn();
    render(<Pagination page={2} pageSize={25} total={60} onChange={onChange} />);
    await userEvent.click(screen.getByRole("button", { name: "Next" }));
    await userEvent.click(screen.getByRole("button", { name: "Previous" }));
    expect(onChange.mock.calls).toEqual([[3], [1]]);
  });

  it("disables Previous on the first page and Next on the last", () => {
    const { rerender } = render(
      <Pagination page={1} pageSize={25} total={60} onChange={vi.fn()} />,
    );
    expect(screen.getByRole("button", { name: "Previous" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Next" })).toBeEnabled();

    rerender(<Pagination page={3} pageSize={25} total={60} onChange={vi.fn()} />);
    expect(screen.getByText("Showing 51–60 of 60")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Next" })).toBeDisabled();
  });

  it("handles an empty result set", () => {
    render(<Pagination page={1} pageSize={25} total={0} onChange={vi.fn()} />);
    expect(screen.getByText("No results")).toBeInTheDocument();
    expect(screen.getByText("Page 1 of 1")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Next" })).toBeDisabled();
  });
});
