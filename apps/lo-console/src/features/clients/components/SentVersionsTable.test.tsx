import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { ClientSentVersion } from "../types";
import { SentVersionsTable } from "./SentVersionsTable";

const VERSIONS: ClientSentVersion[] = [
  {
    id: "v1",
    application_id: "app-1",
    version: 1,
    sent_at: "2026-09-01T12:00:00Z",
    recommended_option_label: "30yr Fixed · Par",
    status: "viewed",
    report_link: "/report/abc123",
  },
];

describe("SentVersionsTable", () => {
  it("shows an empty state with no versions", () => {
    render(<SentVersionsTable versions={[]} />);
    expect(screen.getByText("No quotes sent yet")).toBeInTheDocument();
  });

  it("renders a row per sent version with its recommended option and report link", () => {
    render(<SentVersionsTable versions={VERSIONS} />);
    expect(screen.getByText("30yr Fixed · Par")).toBeInTheDocument();
    expect(screen.getByText("Viewed")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Preview" })).toHaveAttribute("href", "/report/abc123");
  });

  it("shows a dash when there's no recommended option", () => {
    render(<SentVersionsTable versions={[{ ...VERSIONS[0], recommended_option_label: null }]} />);
    expect(screen.getByText("—")).toBeInTheDocument();
  });
});
