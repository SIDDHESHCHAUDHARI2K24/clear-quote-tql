import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ActivityFeed } from "./ActivityFeed";

describe("ActivityFeed", () => {
  it("shows the empty state when nothing has happened yet", () => {
    render(<ActivityFeed items={[]} />);
    expect(screen.getByText("Nothing needs you right now")).toBeInTheDocument();
  });

  it("renders actor, humanized type and client for each event, linking into the workspace", () => {
    render(
      <ActivityFeed
        items={[
          {
            id: "evt-1",
            actor: "System",
            type: "pipeline.priced",
            application_id: "app-1",
            client_name: "Nina Client",
            at: new Date().toISOString(),
          },
        ]}
      />,
    );

    expect(screen.getByText("System")).toBeInTheDocument();
    expect(screen.getByText("pipeline priced")).toBeInTheDocument();
    expect(screen.getByText("· Nina Client")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Nina Client/ })).toHaveAttribute(
      "href",
      "/applications/app-1",
    );
  });
});
