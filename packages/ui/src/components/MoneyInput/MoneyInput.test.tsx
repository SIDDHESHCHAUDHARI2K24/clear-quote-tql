import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";

import { MoneyInput } from "./MoneyInput";

function ControlledMoneyInput({ onChange }: { onChange: (v: string) => void }) {
  const [value, setValue] = useState("");
  return (
    <MoneyInput
      aria-label="Purchase price"
      value={value}
      onChange={(v) => {
        setValue(v);
        onChange(v);
      }}
    />
  );
}

describe("MoneyInput", () => {
  it("emits raw decimal string typed, never a number or reformatted string", async () => {
    const onChange = vi.fn();
    render(<ControlledMoneyInput onChange={onChange} />);
    const input = screen.getByLabelText("Purchase price");
    await userEvent.type(input, "1234.5");

    const lastCall = onChange.mock.calls.at(-1)?.[0];
    expect(lastCall).toBe("1234.5");
    expect(typeof lastCall).toBe("string");
    // never comma-formatted
    expect(onChange.mock.calls.some(([v]) => String(v).includes(","))).toBe(false);
  });

  it("renders empty string and filled state", () => {
    const { rerender } = render(
      <MoneyInput aria-label="Purchase price" value="" onChange={vi.fn()} />,
    );
    expect(screen.getByLabelText("Purchase price")).toHaveValue("");

    rerender(<MoneyInput aria-label="Purchase price" value="342000.00" onChange={vi.fn()} />);
    expect(screen.getByLabelText("Purchase price")).toHaveValue("342000.00");
  });

  it("marks invalid state", () => {
    render(<MoneyInput aria-label="Purchase price" value="abc" invalid onChange={vi.fn()} />);
    expect(screen.getByLabelText("Purchase price")).toHaveAttribute("aria-invalid", "true");
  });

  it("renders a source badge when provided", () => {
    render(
      <MoneyInput
        aria-label="Purchase price"
        value="342000"
        onChange={vi.fn()}
        sourceBadge={{ source: "encompass" }}
      />,
    );
    expect(screen.getByText(/encompass/i)).toBeInTheDocument();
  });
});
