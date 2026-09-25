import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";

import { MultiSelect } from "./MultiSelect";

const OPTIONS = [
  { value: "intake", label: "Intake" },
  { value: "priced", label: "Priced" },
  { value: "sent", label: "Sent" },
];

function Harness({ onChange = vi.fn() }: { onChange?: (v: string[]) => void }) {
  const [value, setValue] = useState<string[]>([]);
  return (
    <div>
      <MultiSelect
        label="Status"
        options={OPTIONS}
        value={value}
        onChange={(next) => {
          setValue(next);
          onChange(next);
        }}
      />
      <button type="button">Outside</button>
    </div>
  );
}

describe("MultiSelect", () => {
  it("opens a labelled checkbox group from the trigger", async () => {
    render(<Harness />);
    const trigger = screen.getByRole("button", { name: /Status/ });
    expect(trigger).toHaveAttribute("aria-expanded", "false");
    expect(trigger).toHaveAccessibleName("Status Any");

    await userEvent.click(trigger);
    expect(trigger).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByRole("group", { name: "Status" })).toBeInTheDocument();
    expect(screen.getAllByRole("checkbox")).toHaveLength(3);
  });

  it("toggles values in option order and summarises the selection", async () => {
    const onChange = vi.fn();
    render(<Harness onChange={onChange} />);
    await userEvent.click(screen.getByRole("button", { name: /Status/ }));

    await userEvent.click(screen.getByLabelText("Sent"));
    await userEvent.click(screen.getByLabelText("Intake"));
    expect(onChange).toHaveBeenLastCalledWith(["intake", "sent"]);
    expect(screen.getByRole("button", { name: /Status/ })).toHaveAccessibleName(
      "Status 2 selected",
    );

    await userEvent.click(screen.getByLabelText("Sent"));
    expect(onChange).toHaveBeenLastCalledWith(["intake"]);
    expect(screen.getByRole("button", { name: /Status/ })).toHaveAccessibleName("Status Intake");
  });

  it("closes on Escape and returns focus to the trigger", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    const trigger = screen.getByRole("button", { name: /Status/ });
    await user.click(trigger);
    await user.click(screen.getByLabelText("Priced"));

    await user.keyboard("{Escape}");
    expect(screen.queryByRole("group")).not.toBeInTheDocument();
    expect(document.activeElement).toBe(trigger);
  });

  it("closes on an outside click", async () => {
    render(<Harness />);
    await userEvent.click(screen.getByRole("button", { name: /Status/ }));
    await userEvent.click(screen.getByRole("button", { name: "Outside" }));
    expect(screen.queryByRole("group")).not.toBeInTheDocument();
  });
});
