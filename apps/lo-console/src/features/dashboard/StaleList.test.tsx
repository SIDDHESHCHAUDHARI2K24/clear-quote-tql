import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { StaleList } from "./StaleList";

describe("StaleList", () => {
  it("shows the empty state when nothing is going stale", () => {
    render(<StaleList items={[]} />);
    expect(screen.getByText("Nothing needs you right now")).toBeInTheDocument();
  });

  it("renders each application's client and age, linking into the workspace", () => {
    render(
      <StaleList items={[{ application_id: "app-9", client_name: "Grace Kim", days_old: 25 }]} />,
    );

    expect(screen.getByText("Grace Kim")).toBeInTheDocument();
    expect(screen.getByText("25 days old")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Grace Kim/ })).toHaveAttribute(
      "href",
      "/applications/app-9",
    );
  });
});
