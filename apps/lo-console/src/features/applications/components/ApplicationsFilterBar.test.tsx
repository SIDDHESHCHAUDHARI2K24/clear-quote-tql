import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { DEFAULT_FILTERS } from "../filters";
import { ApplicationsFilterBar } from "./ApplicationsFilterBar";

describe("ApplicationsFilterBar", () => {
  it("calls onChange when typing a search query", async () => {
    const onChange = vi.fn();
    render(
      <ApplicationsFilterBar
        filters={DEFAULT_FILTERS}
        onChange={onChange}
        onClear={vi.fn()}
        showLoFilter={false}
        loOptions={[]}
      />,
    );
    await userEvent.type(screen.getByLabelText("Search"), "a");
    expect(onChange).toHaveBeenCalledWith({ q: "a" });
  });

  it("toggles a strategy chip", async () => {
    const onChange = vi.fn();
    render(
      <ApplicationsFilterBar
        filters={DEFAULT_FILTERS}
        onChange={onChange}
        onClear={vi.fn()}
        showLoFilter={false}
        loOptions={[]}
      />,
    );
    await userEvent.click(screen.getByRole("button", { name: "LTR" }));
    expect(onChange).toHaveBeenCalledWith({ strategy: ["ltr"] });
  });

  it("toggles the has-property control", async () => {
    const onChange = vi.fn();
    render(
      <ApplicationsFilterBar
        filters={DEFAULT_FILTERS}
        onChange={onChange}
        onClear={vi.fn()}
        showLoFilter={false}
        loOptions={[]}
      />,
    );
    await userEvent.click(screen.getByRole("radio", { name: "Has property" }));
    expect(onChange).toHaveBeenCalledWith({ hasProperty: "true" });
  });

  it("calls onClear", async () => {
    const onClear = vi.fn();
    render(
      <ApplicationsFilterBar
        filters={DEFAULT_FILTERS}
        onChange={vi.fn()}
        onClear={onClear}
        showLoFilter={false}
        loOptions={[]}
      />,
    );
    await userEvent.click(screen.getByRole("button", { name: "Clear filters" }));
    expect(onClear).toHaveBeenCalled();
  });

  it("shows the LO select only for a Manager/Admin", () => {
    const { rerender } = render(
      <ApplicationsFilterBar
        filters={DEFAULT_FILTERS}
        onChange={vi.fn()}
        onClear={vi.fn()}
        showLoFilter={false}
        loOptions={[{ id: "lo-1", full_name: "Jordan Lee" }]}
      />,
    );
    expect(screen.queryByLabelText("LO")).not.toBeInTheDocument();

    rerender(
      <ApplicationsFilterBar
        filters={DEFAULT_FILTERS}
        onChange={vi.fn()}
        onClear={vi.fn()}
        showLoFilter={true}
        loOptions={[{ id: "lo-1", full_name: "Jordan Lee" }]}
      />,
    );
    expect(screen.getByLabelText("LO")).toBeInTheDocument();
    expect(screen.getByText("Jordan Lee")).toBeInTheDocument();
  });
});
