import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { APPLICATION_STATUSES, SOURCE_BADGE_SOURCES } from "@cq/ui";

import GalleryPage from "./page";

describe("Gallery page", () => {
  it("renders every component with at least two fixture states each", () => {
    render(<GalleryPage />);

    // Button — several variants
    expect(screen.getByRole("button", { name: "Primary" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Danger" })).toBeInTheDocument();

    // MoneyInput — filled, empty, invalid, sourced
    expect(screen.getByLabelText("Purchase price (filled)")).toHaveValue("342000.00");
    expect(screen.getByLabelText("Purchase price (empty)")).toHaveValue("");
    expect(screen.getByLabelText("Purchase price (invalid)")).toHaveAttribute(
      "aria-invalid",
      "true",
    );

    // PercentInput — filled, empty
    expect(screen.getByLabelText("Note rate (filled)")).toHaveValue("6.750");
    expect(screen.getByLabelText("Note rate (empty)")).toHaveValue("");

    // Table — rows + empty state
    expect(screen.getByText("30yr Fixed")).toBeInTheDocument();
    expect(screen.getByText("No quotes yet")).toBeInTheDocument();

    // Tabs
    expect(screen.getByRole("tab", { name: /borrowers/i })).toBeInTheDocument();

    // StatusPill — every ApplicationStatus value present
    for (const status of APPLICATION_STATUSES) {
      expect(
        screen.getAllByText(new RegExp(status.replaceAll("_", " "), "i")).length,
      ).toBeGreaterThan(0);
    }

    // SourceBadge — every SourceBadgeSource value present
    expect(screen.getAllByText(/Encompass/).length).toBeGreaterThan(0);
    expect(SOURCE_BADGE_SOURCES.length).toBe(12);

    // Overlay trigger present (closed by default)
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Open overlay" })).toBeInTheDocument();
  });

  it("renders the P5/P6 foundation primitives", () => {
    render(<GalleryPage />);

    expect(screen.getByRole("navigation", { name: "Pagination (middle page)" })).toBeVisible();
    expect(screen.getByText("Showing 26–50 of 212")).toBeInTheDocument();
    expect(screen.getByText("No results")).toBeInTheDocument();
    expect(screen.getByLabelText("Loan officer (filter)")).toHaveValue("");
    expect(screen.getByLabelText("Loan officer (error)")).toHaveAccessibleDescription(
      "Choose a loan officer",
    );
    expect(screen.getByRole("button", { name: /Status \(filter\)/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Open drawer" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "No applications match" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Show success toast" })).toBeInTheDocument();
  });
});
