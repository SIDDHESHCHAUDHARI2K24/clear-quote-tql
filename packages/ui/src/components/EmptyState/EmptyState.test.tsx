import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { EmptyState } from "./EmptyState";

describe("EmptyState", () => {
  it("renders the title as a heading with body and action", () => {
    render(
      <EmptyState
        title="No applications yet"
        body="Start one in a few minutes."
        action={<a href="/apply">Start your application</a>}
      />,
    );
    expect(screen.getByRole("heading", { level: 2, name: "No applications yet" })).toBeVisible();
    expect(screen.getByText("Start one in a few minutes.")).toBeVisible();
    expect(screen.getByRole("link", { name: "Start your application" })).toHaveAttribute(
      "href",
      "/apply",
    );
  });

  it("supports a level-3 heading and no body or action", () => {
    render(<EmptyState title="No results" headingLevel={3} />);
    expect(screen.getByRole("heading", { level: 3, name: "No results" })).toBeVisible();
    expect(screen.queryByRole("link")).not.toBeInTheDocument();
  });
});
