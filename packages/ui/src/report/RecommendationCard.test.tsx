import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { RecommendationCard } from "./RecommendationCard";
import type { ReportRecommendationData } from "./types";

const RECOMMENDATION: ReportRecommendationData = {
  text: "We recommend the par option.",
  lo_note: null,
};

describe("RecommendationCard", () => {
  it("renders the recommendation text", () => {
    render(<RecommendationCard recommendation={RECOMMENDATION} />);
    expect(screen.getByText("We recommend the par option.")).toBeInTheDocument();
  });

  it("renders the LO note when present", () => {
    render(
      <RecommendationCard
        recommendation={{ ...RECOMMENDATION, lo_note: "Happy to walk through the numbers." }}
      />,
    );
    expect(screen.getByText(/Happy to walk through the numbers\./)).toBeInTheDocument();
  });

  it("does not show the alternative-view note by default", () => {
    render(<RecommendationCard recommendation={RECOMMENDATION} />);
    expect(
      screen.queryByText(/You.re viewing an alternative to our recommendation\./),
    ).not.toBeInTheDocument();
  });

  it("shows the alternative-view note when viewingAlternative is true (CQ-022 AC3)", () => {
    render(<RecommendationCard recommendation={RECOMMENDATION} viewingAlternative />);
    expect(
      screen.getByText(/You.re viewing an alternative to our recommendation\./),
    ).toBeInTheDocument();
  });
});
