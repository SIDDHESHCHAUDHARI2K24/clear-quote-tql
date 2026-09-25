import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { SOURCE_BADGE_SOURCES } from "../../types";
import { SourceBadge } from "./SourceBadge";

describe("SourceBadge", () => {
  it("renders every SourceBadgeSource, revert affordance only on lo_override", () => {
    for (const source of SOURCE_BADGE_SOURCES) {
      const onRevert = vi.fn();
      const { container, unmount } = render(<SourceBadge source={source} onRevert={onRevert} />);
      const badge = container.querySelector(`[data-source="${source}"]`);
      expect(badge).not.toBeNull();

      const revertButton = screen.queryByRole("button", { name: "Revert to source" });
      if (source === "lo_override") {
        expect(revertButton).not.toBeNull();
      } else {
        expect(revertButton).toBeNull();
      }
      unmount();
    }
  });

  it("calls onRevert when the revert affordance is clicked", async () => {
    const onRevert = vi.fn();
    render(<SourceBadge source="lo_override" onRevert={onRevert} />);
    await userEvent.click(screen.getByRole("button", { name: "Revert to source" }));
    expect(onRevert).toHaveBeenCalledTimes(1);
  });

  it("does not render a revert affordance when onRevert is omitted, even for lo_override", () => {
    render(<SourceBadge source="lo_override" />);
    expect(screen.queryByRole("button", { name: "Revert to source" })).toBeNull();
  });
});
