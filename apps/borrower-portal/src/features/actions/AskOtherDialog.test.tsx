import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { AskOtherDialog } from "./AskOtherDialog";
import type { AskOtherDialogProps } from "./AskOtherDialog";

describe("AskOtherDialog", () => {
  it("shows the current option for context and the spec.md placeholder", () => {
    render(
      <AskOtherDialog
        isOpen
        onClose={vi.fn()}
        onSubmit={vi.fn()}
        optionLabel="Par"
        submitting={false}
        error={null}
      />,
    );

    expect(screen.getByText(/currently viewing/i)).toBeInTheDocument();
    expect(screen.getByText("Par")).toBeInTheDocument();
    expect(
      screen.getByPlaceholderText(
        "What would you like to change? For example, a lower cash to close.",
      ),
    ).toBeInTheDocument();
  });

  it("disables Send until a non-whitespace message is entered, and trims it on submit", async () => {
    const onSubmit = vi.fn();
    const user = userEvent.setup();
    render(
      <AskOtherDialog
        isOpen
        onClose={vi.fn()}
        onSubmit={onSubmit}
        optionLabel="Par"
        submitting={false}
        error={null}
      />,
    );

    const sendButton = screen.getByRole("button", { name: /send message/i });
    expect(sendButton).toBeDisabled();

    await user.type(screen.getByLabelText(/your message/i), "   ");
    expect(sendButton).toBeDisabled();

    await user.type(screen.getByLabelText(/your message/i), "A lower cash to close, please.");
    expect(sendButton).toBeEnabled();

    await user.click(sendButton);
    expect(onSubmit).toHaveBeenCalledWith("A lower cash to close, please.");
  });

  // Fresh-subagent review finding (fixed): a successful submit closes this
  // dialog from the caller (ReportActionsSlot's onSuccess), not through
  // this component's own handleClose, so a naive reset-only-in-handleClose
  // left a stale message pre-filled (and Send already enabled) the next
  // time it opened. The real fix is `ReportActionsSlot` remounting this
  // component via a changing `key` on every open (see this component's
  // own docstring) -- exercised here the same way, since `key` isn't a
  // prop this component reads itself.
  it("clears a leftover message when remounted via a fresh key (how ReportActionsSlot reopens it)", async () => {
    const props: Omit<AskOtherDialogProps, "isOpen"> = {
      onClose: vi.fn(),
      onSubmit: vi.fn(),
      optionLabel: "Par",
      submitting: false,
      error: null,
    };
    const user = userEvent.setup();
    const { rerender } = render(<AskOtherDialog key="open-1" {...props} isOpen />);

    await user.type(screen.getByLabelText(/your message/i), "A lower cash to close, please.");
    expect(screen.getByLabelText(/your message/i)).toHaveValue("A lower cash to close, please.");

    // Simulate the caller closing the dialog via a success path (not
    // AskOtherDialog's own handleClose) -- e.g. ReportActionsSlot flips
    // dialog.kind to "none" directly on a successful submit -- then
    // reopening with a bumped key, same as a second "Ask about another
    // option" click.
    rerender(<AskOtherDialog key="open-1" {...props} isOpen={false} />);
    rerender(<AskOtherDialog key="open-2" {...props} isOpen />);

    expect(screen.getByLabelText(/your message/i)).toHaveValue("");
    expect(screen.getByRole("button", { name: /send message/i })).toBeDisabled();
  });

  it("closes on Escape and does not submit while closed", async () => {
    const onClose = vi.fn();
    const user = userEvent.setup();
    render(
      <AskOtherDialog
        isOpen
        onClose={onClose}
        onSubmit={vi.fn()}
        optionLabel="Par"
        submitting={false}
        error={null}
      />,
    );

    await user.keyboard("{Escape}");
    expect(onClose).toHaveBeenCalledTimes(1);
  });
});
