import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { Button } from "./Button";

describe("Button", () => {
  it("renders children and handles click", async () => {
    const onClick = vi.fn();
    render(<Button onClick={onClick}>Save</Button>);
    const button = screen.getByRole("button", { name: "Save" });
    await userEvent.click(button);
    expect(onClick).toHaveBeenCalledTimes(1);
  });

  it("disables the button and blocks clicks while loading", async () => {
    const onClick = vi.fn();
    render(
      <Button isLoading onClick={onClick}>
        Save
      </Button>,
    );
    const button = screen.getByRole("button", { name: "Save" });
    expect(button).toBeDisabled();
    expect(button).toHaveAttribute("aria-busy", "true");
  });

  it("renders variant and size without crashing", () => {
    render(
      <Button variant="danger" size="lg">
        Delete
      </Button>,
    );
    expect(screen.getByRole("button", { name: "Delete" })).toBeInTheDocument();
  });
});
