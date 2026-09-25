import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { REPORT_FIXTURES } from "@cq/ui";

import { ReportMatchesSlot } from "./ReportMatchesSlot";

const marcusHale = REPORT_FIXTURES.find((f) => f.key === "marcus_hale")!.viewModel;

describe("ReportMatchesSlot", () => {
  it("renders nothing while matches is empty (CQ-021 fixtures always are, until CQ-023)", () => {
    expect(marcusHale.matches).toHaveLength(0);
    const { container } = render(<ReportMatchesSlot viewModel={marcusHale} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("renders nothing (its own placeholder) even if matches is non-empty, pending CQ-023", () => {
    const withMatches = {
      ...marcusHale,
      matches: [
        {
          matched_property_id: "p1",
          property_image_url: "https://example.test/p1.jpg",
          property_address: "123 Main St",
          bed_bath_sqft: "3bd / 2ba / 1500sqft",
          deal_grade_badge: "Great deal",
          property_tagline: "Strong STR comps nearby",
          price: "300000.00",
        },
      ],
    };
    const { container } = render(<ReportMatchesSlot viewModel={withMatches} />);
    expect(container).toBeEmptyDOMElement();
  });
});
