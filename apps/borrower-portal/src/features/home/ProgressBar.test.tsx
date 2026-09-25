import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ProgressBar } from "./ProgressBar";

describe("ProgressBar", () => {
  it("marks the current step for each of the four covered stages", () => {
    const { rerender } = render(<ProgressBar stage="applied" />);
    expect(screen.getByText("Applied")).toHaveAttribute("aria-current", "step");

    rerender(<ProgressBar stage="in_review" />);
    expect(screen.getByText("In review")).toHaveAttribute("aria-current", "step");

    rerender(<ProgressBar stage="preapproved" />);
    expect(screen.getByText("Pre-approved")).toHaveAttribute("aria-current", "step");

    rerender(<ProgressBar stage="option_selected" />);
    expect(screen.getByText("Option selected")).toHaveAttribute("aria-current", "step");
  });

  it("renders nothing for a stage the 4-step bar doesn't cover", () => {
    const { container, rerender } = render(<ProgressBar stage="closed" />);
    expect(container).toBeEmptyDOMElement();

    rerender(<ProgressBar stage="draft" />);
    expect(container).toBeEmptyDOMElement();
  });
});
