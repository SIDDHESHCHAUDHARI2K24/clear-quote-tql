import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { MatchList } from "./MatchList";
import type { ReportMatchData } from "./types";

function match(overrides: Partial<ReportMatchData> = {}): ReportMatchData {
  return {
    matched_property_id: "listing-1",
    property_image_url: "https://example.test/listing1.jpg",
    property_address: "111 Grove Ave, Davenport, FL 33896",
    bed_bath_sqft: "3 bd · 2 ba · 1,550 sqft",
    deal_grade_badge: "great_buy",
    property_tagline: "Move-in ready Davenport rental",
    price: "220000.00",
    total_monthly_payment: "1380.42",
    rent_estimate: "2250.00",
    rent_label: "Market rent (LTR)",
    monthly_cashflow: "869.58",
    cash_to_close: "60665.63",
    cap_rate_pct: "9.20",
    year1_tax_savings: "15616.00",
    ...overrides,
  };
}

describe("MatchList", () => {
  it("renders nothing when there are no matches (spec.md: section hidden entirely)", () => {
    const { container } = render(<MatchList matches={[]} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("renders the section title and subtitle", () => {
    render(<MatchList matches={[match()]} />);
    expect(screen.getByText("Your top 3 property matches")).toBeInTheDocument();
    expect(
      screen.getByText("Selected for your budget and markets, each run through the same numbers"),
    ).toBeInTheDocument();
  });

  it("renders one card per match, numbered in order", () => {
    render(
      <MatchList
        matches={[
          match({ matched_property_id: "a" }),
          match({ matched_property_id: "b" }),
          match({ matched_property_id: "c" }),
        ]}
      />,
    );
    expect(screen.getAllByTestId("match-card")).toHaveLength(3);
    expect(screen.getByText("Match 1")).toBeInTheDocument();
    expect(screen.getByText("Match 2")).toBeInTheDocument();
    expect(screen.getByText("Match 3")).toBeInTheDocument();
  });

  it("uses a responsive grid: one column by default, three from the lg breakpoint (AC8)", () => {
    render(<MatchList matches={[match()]} />);
    const grid = screen.getByTestId("match-list").querySelector(":scope > div");
    expect(grid?.className).toContain("grid-cols-1");
    expect(grid?.className).toContain("lg:grid-cols-3");
  });
});
