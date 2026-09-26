import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { ClientDetail } from "../types";
import { ClientDetailHeader } from "./ClientDetailHeader";

const CLIENT: ClientDetail = {
  id: "1",
  name: "Marcus Hale",
  email: "marcus.hale@clearquote-demo.test",
  phone: "555-0100",
  lo_id: "lo-1",
  lo_name: "Jordan Lee",
  created_at: "2026-09-01T12:00:00Z",
  applications: [],
  sent_versions: [],
  activity: [],
};

describe("ClientDetailHeader", () => {
  it("shows the client's name, contact details and assigned LO", () => {
    render(<ClientDetailHeader client={CLIENT} />);
    expect(screen.getByRole("heading", { level: 1, name: "Marcus Hale" })).toBeInTheDocument();
    expect(screen.getByText("marcus.hale@clearquote-demo.test")).toBeInTheDocument();
    expect(screen.getByText("555-0100")).toBeInTheDocument();
    expect(screen.getByText("Jordan Lee")).toBeInTheDocument();
  });

  it("omits the phone line when there's none", () => {
    render(<ClientDetailHeader client={{ ...CLIENT, phone: null }} />);
    expect(screen.queryByText("555-0100")).not.toBeInTheDocument();
  });
});
