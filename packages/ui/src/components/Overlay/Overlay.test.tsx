import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
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

  it("moves focus into the dialog when it opens", () => {
    render(
      <Overlay isOpen onClose={vi.fn()} title="Edit quote">
        <button type="button">Save</button>
      </Overlay>,
    );
    expect(screen.getByRole("dialog")).toContainElement(document.activeElement as HTMLElement);
  });

  it("traps Tab focus within the dialog", async () => {
    const user = userEvent.setup();
    render(
      <Overlay isOpen onClose={vi.fn()} title="Edit quote">
        <button type="button">First</button>
        <button type="button">Last</button>
      </Overlay>,
    );
    const close = screen.getByLabelText("Close");
    const first = screen.getByRole("button", { name: "First" });
    const last = screen.getByRole("button", { name: "Last" });

    // Focus starts on the first focusable element in DOM order (the close
    // button), and Shift+Tab from there wraps to the last focusable
    // element instead of leaving the dialog.
    expect(document.activeElement).toBe(close);
    await user.tab({ shift: true });
    expect(document.activeElement).toBe(last);

    // Tab from the last focusable element wraps back to the first.
    await user.tab();
    expect(document.activeElement).toBe(close);
    await user.tab();
    expect(document.activeElement).toBe(first);
  });

  it("returns focus to the previously focused element when it closes", () => {
    function Harness() {
      const [isOpen, setIsOpen] = useState(false);
      return (
        <div>
          <button type="button" onClick={() => setIsOpen(true)}>
            Open
          </button>
          <Overlay isOpen={isOpen} onClose={() => setIsOpen(false)} title="Edit quote">
            <button type="button">Save</button>
          </Overlay>
        </div>
      );
    }
    render(<Harness />);
    const trigger = screen.getByRole("button", { name: "Open" });
    trigger.focus();
    fireEvent.click(trigger);
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(document.activeElement).not.toBe(trigger);

    fireEvent.click(screen.getByLabelText("Close"));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(document.activeElement).toBe(trigger);
  });

  it("does not steal focus back to the first element while typing, even when onClose is a new closure every render", async () => {
    // Regression for a real bug (CQ-016): an `onClose` closure that isn't
    // memoized (very common -- it often closes over other local state)
    // must not re-trigger the initial-focus effect on every parent
    // re-render, or a later space/enter keystroke "clicks" whatever
    // element focus got stolen back to (often a button), closing the
    // dialog out from under the user.
    const user = userEvent.setup();
    function Harness() {
      const [isOpen, setIsOpen] = useState(true);
      const [text, setText] = useState("");
      return (
        <Overlay isOpen={isOpen} onClose={() => setIsOpen(false)} title="Edit quote">
          <input aria-label="Note" value={text} onChange={(e) => setText(e.target.value)} />
        </Overlay>
      );
    }
    render(<Harness />);

    await user.type(screen.getByLabelText("Note"), "hello world");

    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(screen.getByLabelText("Note")).toHaveValue("hello world");
  });
});
