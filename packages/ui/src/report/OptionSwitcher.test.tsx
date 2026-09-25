import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { OptionSwitcher } from "./OptionSwitcher";
import marcusHale from "./__fixtures__/marcus_hale.json";
import type { ReportViewModelData } from "./types";

const marcus = marcusHale as ReportViewModelData;

describe("OptionSwitcher", () => {
  it("renders one pill per option, recommended first with a star", () => {
    render(
      <OptionSwitcher
        options={marcus.options}
        selectedId={marcus.options[0].quote_id}
        onChange={() => {}}
      />,
    );

    const radios = screen.getAllByRole("radio");
    expect(radios).toHaveLength(marcus.options.length);
    expect(radios[0]).toHaveTextContent("Par");
    expect(radios[0]).toHaveAttribute("aria-checked", "true");
    expect(radios[0].textContent).toContain("★");
  });

  it("calls onChange with the clicked option's quote_id", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(
      <OptionSwitcher
        options={marcus.options}
        selectedId={marcus.options[0].quote_id}
        onChange={onChange}
      />,
    );

    await user.click(screen.getByRole("radio", { name: /buydown/i }));
    expect(onChange).toHaveBeenCalledWith(marcus.options[1].quote_id);
  });
});
