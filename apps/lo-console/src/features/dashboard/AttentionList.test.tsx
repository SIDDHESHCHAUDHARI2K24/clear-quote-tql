import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { AttentionList } from "./AttentionList";

describe("AttentionList", () => {
  it("shows the empty state when there is nothing to review", () => {
    render(<AttentionList items={[]} />);
    expect(screen.getByText("Nothing needs you right now")).toBeInTheDocument();
  });

  it("renders each application's client, status, reason and age as a link into the workspace", () => {
    render(
      <AttentionList
        items={[
          {
            application_id: "app-1",
            client_name: "Aisha Coleman",
            status: "needs_attention",
            reason: "Cannot price: missing Occupancy",
            age_days: 1,
          },
          {
            application_id: "app-2",
            client_name: "Luis Romero",
            status: "option_selected",
            reason: "30yr Fixed at 7.125%",
            age_days: 0,
          },
        ]}
      />,
    );

    expect(screen.getByText("Aisha Coleman")).toBeInTheDocument();
    expect(screen.getByText("Cannot price: missing Occupancy")).toBeInTheDocument();
    expect(screen.getByText("Needs attention")).toBeInTheDocument();
    expect(screen.getByText("1 day ago")).toBeInTheDocument();

    expect(screen.getByText("Luis Romero")).toBeInTheDocument();
    expect(screen.getByText("30yr Fixed at 7.125%")).toBeInTheDocument();
    expect(screen.getByText("today")).toBeInTheDocument();

    expect(screen.getByRole("link", { name: /Aisha Coleman/ })).toHaveAttribute(
      "href",
      "/applications/app-1",
    );
  });
});
