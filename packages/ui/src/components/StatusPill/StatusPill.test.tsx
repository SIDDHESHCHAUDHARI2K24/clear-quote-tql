import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { APPLICATION_STATUSES, APPLICATION_STATUS_TONE } from "../../types";
import { StatusPill } from "./StatusPill";

describe("StatusPill", () => {
  it("renders every ApplicationStatus with its pinned tone", () => {
    for (const status of APPLICATION_STATUSES) {
      const { container, unmount } = render(<StatusPill status={status} />);
      const pill = container.querySelector(`[data-status="${status}"]`);
      expect(pill).not.toBeNull();
      expect(pill).toHaveAttribute("data-tone", APPLICATION_STATUS_TONE[status]);
      unmount();
    }
  });

  it("supports the sm size", () => {
    render(<StatusPill status="priced" size="sm" />);
    expect(screen.getByText("Priced")).toBeInTheDocument();
  });
});
