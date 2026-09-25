import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { MoveForwardDialog } from "./MoveForwardDialog";

describe("MoveForwardDialog", () => {
  it("shows the exact spec.md wording with the option label and LO first name", () => {
    render(
      <MoveForwardDialog
        isOpen
        onClose={vi.fn()}
        onConfirm={vi.fn()}
        optionLabel="Buydown"
        loFirstName="Jordan"
        submitting={false}
        error={null}
      />,
    );

    expect(screen.getByText(/This tells Jordan you.d like to go ahead with/i)).toBeInTheDocument();
    expect(screen.getByText("Buydown")).toBeInTheDocument();
    expect(screen.getByText(/isn.t locked yet/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Yes, let Jordan know" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Cancel" })).toBeInTheDocument();
  });

  // AC7: dialogs trap focus and close on Escape (packages/ui's Overlay,
  // CQ-016) -- verified here at this dialog's own level, not just
  // Overlay's generic suite, since AC7 names this item's dialogs
  // specifically.
  it("traps focus within the dialog and closes on Escape", async () => {
    const onClose = vi.fn();
    const user = userEvent.setup();
    render(
      <MoveForwardDialog
        isOpen
        onClose={onClose}
        onConfirm={vi.fn()}
        optionLabel="Buydown"
        loFirstName="Jordan"
        submitting={false}
        error={null}
      />,
    );

    // Overlay's own header close button is the first focusable element in
    // DOM order (before the footer's Cancel/Confirm), and gets focus on
    // open.
    const closeButton = screen.getByLabelText("Close");
    const cancelButton = screen.getByRole("button", { name: "Cancel" });
    const confirmButton = screen.getByRole("button", { name: "Yes, let Jordan know" });

    expect(closeButton).toHaveFocus();

    await user.tab();
    expect(cancelButton).toHaveFocus();

    await user.tab();
    expect(confirmButton).toHaveFocus();

    // Tabbing past the last focusable element wraps back to the first
    // (the focus trap), instead of escaping to the rest of the page.
    await user.tab();
    expect(closeButton).toHaveFocus();

    await user.keyboard("{Escape}");
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("disables Cancel and shows a loading state on Confirm while submitting", () => {
    render(
      <MoveForwardDialog
        isOpen
        onClose={vi.fn()}
        onConfirm={vi.fn()}
        optionLabel="Buydown"
        loFirstName="Jordan"
        submitting
        error={null}
      />,
    );

    expect(screen.getByRole("button", { name: "Cancel" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Yes, let Jordan know" })).toHaveAttribute(
      "aria-busy",
      "true",
    );
  });

  it("shows the error message when one is passed", () => {
    render(
      <MoveForwardDialog
        isOpen
        onClose={vi.fn()}
        onConfirm={vi.fn()}
        optionLabel="Buydown"
        loFirstName="Jordan"
        submitting={false}
        error="Something went wrong. Try again."
      />,
    );

    expect(screen.getByRole("alert")).toHaveTextContent("Something went wrong. Try again.");
  });
});
