import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Card } from "./Card";

describe("Card", () => {
  it("renders title, actions and children", () => {
    render(
      <Card title="Application" actions={<button>Edit</button>}>
        <p>Body content</p>
      </Card>,
    );
    expect(screen.getByText("Application")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Edit" })).toBeInTheDocument();
    expect(screen.getByText("Body content")).toBeInTheDocument();
  });

  it("renders without a header when no title or actions are given", () => {
    render(<Card>Just content</Card>);
    expect(screen.getByText("Just content")).toBeInTheDocument();
  });
});
