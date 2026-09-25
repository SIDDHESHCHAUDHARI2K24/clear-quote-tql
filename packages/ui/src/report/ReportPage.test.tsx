import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { REPORT_FIXTURES } from "./fixtures";
import { ReportPage } from "./ReportPage";

const marcusHale = REPORT_FIXTURES.find((f) => f.key === "marcus_hale")!;
const priyaNairSuperseded = REPORT_FIXTURES.find((f) => f.key === "priya_nair_superseded")!;

describe("ReportPage", () => {
  it("renders nothing extra when renderMatches/renderActions are omitted (CQ-019/CQ-021 callers)", () => {
    render(<ReportPage viewModel={marcusHale.viewModel} />);
    expect(screen.queryByTestId("matches-slot")).not.toBeInTheDocument();
    expect(screen.queryByTestId("actions-slot")).not.toBeInTheDocument();
  });

  it("renders the matches slot via renderMatches (CQ-022/CQ-023 wiring, plan.md D3)", () => {
    render(
      <ReportPage
        viewModel={marcusHale.viewModel}
        renderMatches={(vm) => <div data-testid="matches-slot">{vm.matches.length} matches</div>}
      />,
    );
    expect(screen.getByTestId("matches-slot")).toHaveTextContent("0 matches");
  });

  it("renders the actions slot via renderActions, passing the selected option (CQ-022/CQ-024 wiring)", () => {
    render(
      <ReportPage
        viewModel={marcusHale.viewModel}
        renderActions={(_vm, selected) => <div data-testid="actions-slot">{selected.quote_id}</div>}
      />,
    );
    expect(screen.getByTestId("actions-slot")).toHaveTextContent(
      marcusHale.viewModel.options[0]!.quote_id,
    );
  });

  it("passes newestReportHref through to SupersededBanner", () => {
    render(
      <ReportPage
        viewModel={priyaNairSuperseded.viewModel}
        newestReportHref="/report/newest-token"
      />,
    );
    const link = screen.getByRole("link", { name: "Open your most recent report" });
    expect(link).toHaveAttribute("href", "/report/newest-token");
  });

  it("starts on initialSelectedId when it matches a real option (CQ-022 AC3: ?option= on reload)", () => {
    const buydown = marcusHale.viewModel.options.find((o) => !o.recommended)!;
    render(<ReportPage viewModel={marcusHale.viewModel} initialSelectedId={buydown.quote_id} />);

    const radio = screen.getByRole("radio", { name: new RegExp(buydown.label) });
    expect(radio).toHaveAttribute("aria-checked", "true");
  });

  it("falls back to the first (recommended) option when initialSelectedId doesn't match any option", () => {
    render(<ReportPage viewModel={marcusHale.viewModel} initialSelectedId="not-a-real-id" />);

    const firstOption = marcusHale.viewModel.options[0]!;
    const radio = screen.getByRole("radio", { name: new RegExp(firstOption.label) });
    expect(radio).toHaveAttribute("aria-checked", "true");
  });

  it("calls onSelectionChange with the new quote_id when the switcher is clicked", async () => {
    const user = userEvent.setup();
    const onSelectionChange = vi.fn();
    render(<ReportPage viewModel={marcusHale.viewModel} onSelectionChange={onSelectionChange} />);

    const buydown = marcusHale.viewModel.options.find((o) => !o.recommended)!;
    await user.click(screen.getByRole("radio", { name: new RegExp(buydown.label) }));

    expect(onSelectionChange).toHaveBeenCalledWith(buydown.quote_id);
  });

  it("shows the alternative-view note only once a non-recommended option is selected (AC3)", async () => {
    const user = userEvent.setup();
    render(<ReportPage viewModel={marcusHale.viewModel} />);

    expect(
      screen.queryByText(/You.re viewing an alternative to our recommendation\./),
    ).not.toBeInTheDocument();

    const buydown = marcusHale.viewModel.options.find((o) => !o.recommended)!;
    await user.click(screen.getByRole("radio", { name: new RegExp(buydown.label) }));

    expect(
      screen.getByText(/You.re viewing an alternative to our recommendation\./),
    ).toBeInTheDocument();
  });
});
