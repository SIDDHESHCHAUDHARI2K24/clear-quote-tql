import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ConsentBanner } from "./ConsentBanner";

describe("ConsentBanner", () => {
  it("links to the credit-check task for the given consent id", () => {
    render(<ConsentBanner consentId="c1" />);
    expect(
      screen.getByText("Your loan officer needs your permission for a credit check."),
    ).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Review and authorize" })).toHaveAttribute(
      "href",
      "/tasks/credit-check/c1",
    );
  });
});
