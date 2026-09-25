import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { Collapsible } from "./Collapsible";

describe("Collapsible", () => {
  it("starts closed by default: content mounted but CSS-hidden, not the toggle button", () => {
    render(
      <Collapsible label="See the full breakdown">
        <p>Breakdown content</p>
      </Collapsible>,
    );

    const button = screen.getByRole("button", { name: "See the full breakdown" });
    expect(button).toHaveAttribute("aria-expanded", "false");

    // Content mounts unconditionally (CQ-022 AC6: print needs it in the DOM
    // even while collapsed) -- `.hidden` (not the native `hidden`
    // attribute, per Collapsible.tsx's own docstring) drives the closed
    // state on screen.
    const content = screen.getByText("Breakdown content").closest("div")!;
    expect(content.classList.contains("hidden")).toBe(true);
    expect(content.classList.contains("print:block")).toBe(true);

    // The toggle button itself is `print:hidden` (spec.md AC6: "no ...
    // buttons" in print).
    expect(button.className).toContain("print:hidden");
  });

  it("opens on click: content's `.hidden` class is removed", async () => {
    const user = userEvent.setup();
    render(
      <Collapsible label="See the full breakdown">
        <p>Breakdown content</p>
      </Collapsible>,
    );

    await user.click(screen.getByRole("button", { name: "See the full breakdown" }));

    expect(screen.getByRole("button", { name: "See the full breakdown" })).toHaveAttribute(
      "aria-expanded",
      "true",
    );
    const content = screen.getByText("Breakdown content").closest("div")!;
    expect(content.classList.contains("hidden")).toBe(false);
  });

  it("respects defaultOpen", () => {
    render(
      <Collapsible label="See all 3 options we priced" defaultOpen>
        <p>Comparison content</p>
      </Collapsible>,
    );

    const content = screen.getByText("Comparison content").closest("div")!;
    expect(content.classList.contains("hidden")).toBe(false);
  });
});
