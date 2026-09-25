import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { REPORT_FIXTURES } from "@cq/ui";

import { ReportActionsSlot } from "./ReportActionsSlot";

const marcusHale = REPORT_FIXTURES.find((f) => f.key === "marcus_hale")!.viewModel;
const marcusHaleExpired = REPORT_FIXTURES.find((f) => f.key === "marcus_hale_expired")!.viewModel;

describe("ReportActionsSlot", () => {
  it("renders both actions disabled with a 'Coming soon' caption", () => {
    render(<ReportActionsSlot viewModel={marcusHale} selectedOption={marcusHale.options[0]!} />);

    const moveForward = screen.getByRole("button", {
      name: /move forward with this option/i,
    });
    const askAnother = screen.getByRole("button", { name: /ask about another option/i });
    expect(moveForward).toBeDisabled();
    expect(askAnother).toBeDisabled();
    expect(screen.getByText("Coming soon")).toBeInTheDocument();
  });

  it("carries the selected option's quote_id for CQ-024 to read later", () => {
    render(<ReportActionsSlot viewModel={marcusHale} selectedOption={marcusHale.options[0]!} />);

    expect(screen.getByTestId("actions-slot")).toHaveAttribute(
      "data-selected-quote-id",
      marcusHale.options[0]!.quote_id,
    );
  });

  it("renders nothing once the report has expired (spec.md: hides the actions)", () => {
    const { container } = render(
      <ReportActionsSlot
        viewModel={marcusHaleExpired}
        selectedOption={marcusHaleExpired.options[0]!}
      />,
    );
    expect(container).toBeEmptyDOMElement();
  });
});
