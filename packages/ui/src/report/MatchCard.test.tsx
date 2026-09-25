import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { MatchCard } from "./MatchCard";
import type { ReportMatchData } from "./types";

const LTR_MATCH: ReportMatchData = {
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
};

const PRIMARY_MATCH: ReportMatchData = {
  ...LTR_MATCH,
  matched_property_id: "listing-2",
  rent_estimate: null,
  rent_label: null,
  monthly_cashflow: null,
  cap_rate_pct: null,
  year1_tax_savings: null,
};

describe("MatchCard", () => {
  it("renders the price, address and beds/baths/sqft", () => {
    render(<MatchCard match={LTR_MATCH} index={1} />);
    expect(screen.getByText("$220,000")).toBeInTheDocument();
    expect(screen.getByText("111 Grove Ave, Davenport, FL 33896")).toBeInTheDocument();
    expect(screen.getByText("3 bd · 2 ba · 1,550 sqft")).toBeInTheDocument();
    expect(screen.getByText("Match 1")).toBeInTheDocument();
  });

  it("renders every investment field for an LTR match", () => {
    render(<MatchCard match={LTR_MATCH} index={1} />);
    expect(screen.getByText("Market rent (LTR)")).toBeInTheDocument();
    expect(screen.getByText("$2,250.00")).toBeInTheDocument();
    expect(screen.getByText("Monthly cashflow")).toBeInTheDocument();
    expect(screen.getByText("$869.58")).toBeInTheDocument();
    expect(screen.getByText("Est. cap rate")).toBeInTheDocument();
    expect(screen.getByText("9.20%")).toBeInTheDocument();
    expect(screen.getByText("Yr 1 cost seg tax savings")).toBeInTheDocument();
    expect(screen.getByText("$15,616.00")).toBeInTheDocument();
  });

  it("renders a negative monthly cashflow with the danger tone", () => {
    render(<MatchCard match={{ ...LTR_MATCH, monthly_cashflow: "-50.00" }} index={1} />);
    const cashflowValue = screen.getByText("-$50.00");
    expect(cashflowValue.className).toContain("text-status-danger");
  });

  it("omits rent, cashflow, cap rate and tax savings for a primary match (AC5)", () => {
    render(<MatchCard match={PRIMARY_MATCH} index={1} />);
    expect(screen.queryByText("Market rent (LTR)")).not.toBeInTheDocument();
    expect(screen.queryByText("Monthly cashflow")).not.toBeInTheDocument();
    expect(screen.queryByText("Est. cap rate")).not.toBeInTheDocument();
    expect(screen.queryByText("Yr 1 cost seg tax savings")).not.toBeInTheDocument();
    // Still shows the always-present fields.
    expect(screen.getByText("Total monthly payment")).toBeInTheDocument();
    expect(screen.getByText("Cash to close")).toBeInTheDocument();
  });

  it("renders the deal grade badge and tagline", () => {
    render(<MatchCard match={LTR_MATCH} index={1} />);
    expect(screen.getByText("Great buy")).toBeInTheDocument();
    expect(screen.getByText("Move-in ready Davenport rental")).toBeInTheDocument();
  });
});
