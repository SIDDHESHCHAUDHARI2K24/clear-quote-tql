import { render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { REPORT_FIXTURES } from "@cq/ui";

import ReportGalleryPage from "./page";

// AC6 (partial -- the full Playwright console/axe check lands once the
// foundation unit's Playwright setup merges, per the CQ-021 worker
// instructions): a console.error/warn during render usually means a broken
// prop, a missing key, or an accessibility-relevant React warning. This
// Vitest check runs today, without a browser.
describe("Report gallery page (Borrower Portal)", () => {
  let errorSpy: ReturnType<typeof vi.spyOn>;
  let warnSpy: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    errorSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    warnSpy = vi.spyOn(console, "warn").mockImplementation(() => {});
  });

  afterEach(() => {
    errorSpy.mockRestore();
    warnSpy.mockRestore();
  });

  it("renders every fixture with no console errors or warnings", () => {
    render(<ReportGalleryPage />);

    for (const fixture of REPORT_FIXTURES) {
      expect(screen.getByText(fixture.title)).toBeInTheDocument();
    }

    expect(errorSpy).not.toHaveBeenCalled();
    expect(warnSpy).not.toHaveBeenCalled();
  });
});
