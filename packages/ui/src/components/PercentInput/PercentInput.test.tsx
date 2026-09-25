import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";

import { PercentInput } from "./PercentInput";

function ControlledPercentInput({ onChange }: { onChange: (v: string) => void }) {
  const [value, setValue] = useState("");
  return (
    <PercentInput
      aria-label="Note rate"
      value={value}
      onChange={(v) => {
        setValue(v);
        onChange(v);
      }}
    />
  );
}

describe("PercentInput", () => {
  it("emits raw decimal string typed, never a number", async () => {
    const onChange = vi.fn();
    render(<ControlledPercentInput onChange={onChange} />);
    const input = screen.getByLabelText("Note rate");
    await userEvent.type(input, "7.500");

    const lastCall = onChange.mock.calls.at(-1)?.[0];
    expect(lastCall).toBe("7.500");
    expect(typeof lastCall).toBe("string");
  });

  it("renders empty and filled states", () => {
    const { rerender } = render(
      <PercentInput aria-label="Note rate" value="" onChange={vi.fn()} />,
    );
    expect(screen.getByLabelText("Note rate")).toHaveValue("");

    rerender(<PercentInput aria-label="Note rate" value="7.500" onChange={vi.fn()} />);
    expect(screen.getByLabelText("Note rate")).toHaveValue("7.500");
  });

  it("marks invalid state", () => {
    render(<PercentInput aria-label="Note rate" value="xx" invalid onChange={vi.fn()} />);
    expect(screen.getByLabelText("Note rate")).toHaveAttribute("aria-invalid", "true");
  });
});
