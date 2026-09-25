import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { REPORT_FIXTURES } from "@cq/ui";

import { ReportMatchesSlot } from "./ReportMatchesSlot";

const marcusHale = REPORT_FIXTURES.find((f) => f.key === "marcus_hale")!.viewModel;
const kathleen = REPORT_FIXTURES.find((f) => f.key === "kathleen_mcreynolds")!.viewModel;

describe("ReportMatchesSlot", () => {
  it("renders nothing while matches is empty (CQ-023 AC3/AC4)", () => {
    expect(marcusHale.matches).toHaveLength(0);
    const { container } = render(<ReportMatchesSlot viewModel={marcusHale} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("renders the match list when matches is non-empty (Kathleen McReynolds fixture)", () => {
    expect(kathleen.matches.length).toBeGreaterThan(0);
    render(<ReportMatchesSlot viewModel={kathleen} />);

    expect(screen.getByText("Your top 3 property matches")).toBeInTheDocument();
    expect(screen.getAllByTestId("match-card")).toHaveLength(kathleen.matches.length);
  });
});
