import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { SupersededBanner } from "./SupersededBanner";

describe("SupersededBanner", () => {
  it("renders nothing when not superseded", () => {
    const { container } = render(<SupersededBanner superseded={false} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("renders the fallback text with no link when newestReportHref is omitted", () => {
    render(<SupersededBanner superseded />);
    expect(screen.getByRole("alert")).toBeInTheDocument();
    expect(screen.queryByRole("link")).not.toBeInTheDocument();
    expect(
      screen.getByText(/Open your most recent email from your loan officer/),
    ).toBeInTheDocument();
  });

  it("renders a link to the newest version's report when newestReportHref is given (CQ-022)", () => {
    render(<SupersededBanner superseded newestReportHref="/report/newest-token" />);
    const link = screen.getByRole("link", { name: "Open your most recent report" });
    expect(link).toHaveAttribute("href", "/report/newest-token");
  });
});
