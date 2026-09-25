import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ToastProvider, useToast } from "./Toast";

function Trigger({ durationMs }: { durationMs?: number }) {
  const { show } = useToast();
  return (
    <button type="button" onClick={() => show("Saved", { tone: "success", durationMs })}>
      Save
    </button>
  );
}

describe("Toast", () => {
  afterEach(() => {
    vi.useRealTimers();
  });

  it("announces messages in a polite live region", async () => {
    render(
      <ToastProvider>
        <Trigger />
      </ToastProvider>,
    );
    const region = screen.getByRole("status");
    expect(region).toHaveAttribute("aria-live", "polite");
    expect(region).toBeEmptyDOMElement();

    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(region).toHaveTextContent("Saved");
  });

  it("auto-dismisses after the duration", () => {
    vi.useFakeTimers();
    render(
      <ToastProvider>
        <Trigger durationMs={1000} />
      </ToastProvider>,
    );
    act(() => {
      screen.getByRole("button", { name: "Save" }).click();
    });
    expect(screen.getByRole("status")).toHaveTextContent("Saved");

    act(() => {
      vi.advanceTimersByTime(1000);
    });
    expect(screen.getByRole("status")).not.toHaveTextContent("Saved");
  });

  it("can be dismissed by the user", async () => {
    render(
      <ToastProvider>
        <Trigger durationMs={0} />
      </ToastProvider>,
    );
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    await userEvent.click(screen.getByRole("button", { name: "Dismiss notification" }));
    expect(screen.getByRole("status")).toBeEmptyDOMElement();
  });

  it("throws a clear error outside a provider", () => {
    const spy = vi.spyOn(console, "error").mockImplementation(() => {});
    expect(() => render(<Trigger />)).toThrow("useToast must be used inside a <ToastProvider>");
    spy.mockRestore();
  });
});
