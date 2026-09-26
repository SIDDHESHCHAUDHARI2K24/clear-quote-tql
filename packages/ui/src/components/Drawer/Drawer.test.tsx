import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";

import { Drawer } from "./Drawer";

describe("Drawer", () => {
  it("renders nothing when closed", () => {
    render(
      <Drawer isOpen={false} onClose={vi.fn()} title="Activity">
        Body
      </Drawer>,
    );
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("renders a labelled modal dialog with footer", () => {
    render(
      <Drawer isOpen onClose={vi.fn()} title="Activity" footer={<button>Done</button>}>
        Timeline
      </Drawer>,
    );
    const dialog = screen.getByRole("dialog", { name: "Activity" });
    expect(dialog).toHaveAttribute("aria-modal", "true");
    expect(screen.getByText("Timeline")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Done" })).toBeInTheDocument();
  });

  it("closes on Escape, the close button and the backdrop", async () => {
    const onClose = vi.fn();
    const user = userEvent.setup();
    render(
      <Drawer isOpen onClose={onClose} title="Activity">
        Body
      </Drawer>,
    );
    await user.keyboard("{Escape}");
    await user.click(screen.getByLabelText("Close"));
    await user.click(screen.getByTestId("drawer-backdrop"));
    expect(onClose).toHaveBeenCalledTimes(3);
  });

  it("traps Tab focus inside the panel", async () => {
    const user = userEvent.setup();
    render(
      <Drawer isOpen onClose={vi.fn()} title="Activity">
        <button type="button">Older</button>
      </Drawer>,
    );
    const close = screen.getByLabelText("Close");
    const older = screen.getByRole("button", { name: "Older" });
    expect(document.activeElement).toBe(close);
    await user.tab();
    expect(document.activeElement).toBe(older);
    await user.tab();
    expect(document.activeElement).toBe(close);
    await user.tab({ shift: true });
    expect(document.activeElement).toBe(older);
  });

  it("returns focus to the opener when it closes", () => {
    function Harness() {
      const [isOpen, setIsOpen] = useState(false);
      return (
        <>
          <button type="button" onClick={() => setIsOpen(true)}>
            Activity
          </button>
          <Drawer isOpen={isOpen} onClose={() => setIsOpen(false)} title="Activity log">
            Body
          </Drawer>
        </>
      );
    }
    render(<Harness />);
    const opener = screen.getByRole("button", { name: "Activity" });
    opener.focus();
    fireEvent.click(opener);
    expect(document.activeElement).not.toBe(opener);
    fireEvent.click(screen.getByLabelText("Close"));
    expect(document.activeElement).toBe(opener);
  });
});
