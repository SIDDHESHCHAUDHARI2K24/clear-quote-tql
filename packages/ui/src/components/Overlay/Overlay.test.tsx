import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { Overlay } from "./Overlay";

describe("Overlay", () => {
  it("renders nothing when closed", () => {
    render(
      <Overlay isOpen={false} onClose={vi.fn()} title="Edit quote">
        Body
      </Overlay>,
    );
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("renders title, children and footer when open", () => {
    render(
      <Overlay isOpen onClose={vi.fn()} title="Edit quote" footer={<button>Save</button>}>
        Body content
      </Overlay>,
    );
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(screen.getByText("Edit quote")).toBeInTheDocument();
    expect(screen.getByText("Body content")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Save" })).toBeInTheDocument();
  });

  it("calls onClose when the backdrop or close button is clicked", async () => {
    const onClose = vi.fn();
    render(
      <Overlay isOpen onClose={onClose} title="Edit quote">
        Body
      </Overlay>,
    );
    await userEvent.click(screen.getByLabelText("Close"));
    expect(onClose).toHaveBeenCalledTimes(1);

    await userEvent.click(screen.getByTestId("overlay-backdrop"));
    expect(onClose).toHaveBeenCalledTimes(2);
  });
});
