import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

const { pushMock } = vi.hoisted(() => ({ pushMock: vi.fn() }));

vi.mock("next/navigation", () => ({
  usePathname: () => "/applications/app-1/housing",
  useRouter: () => ({ push: pushMock, replace: vi.fn() }),
}));

import { TabRail } from "./TabRail";
import { makeSummary } from "./test-fixtures";

// spec.md AC4: a red count badge for a flagged tab, a green check for ok,
// a grey dot for pending; clicking a tab navigates to its route.
describe("TabRail (AC4)", () => {
  it("shows a flagged badge with the count and marks the active tab from the URL", () => {
    const tabs = makeSummary({
      tabs: [
        { tab: "borrowers", state: "ok", flag_count: 0 },
        { tab: "housing", state: "flagged", flag_count: 2 },
        { tab: "credit", state: "pending", flag_count: 0 },
        { tab: "assets", state: "ok", flag_count: 0 },
        { tab: "property", state: "ok", flag_count: 0 },
        { tab: "pricing", state: "ok", flag_count: 0 },
        { tab: "send", state: "pending", flag_count: 0 },
      ],
    }).tabs;

    render(<TabRail applicationId="app-1" tabs={tabs} />);

    expect(screen.getByRole("tab", { name: /housing/i })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByLabelText("2 flags")).toBeInTheDocument();
    expect(screen.getAllByLabelText("Pending").length).toBeGreaterThan(0);
  });

  it("navigates to the tab's route when clicked", async () => {
    const user = userEvent.setup();
    const tabs = makeSummary().tabs;
    render(<TabRail applicationId="app-1" tabs={tabs} />);

    await user.click(screen.getByRole("tab", { name: /borrowers/i }));

    expect(pushMock).toHaveBeenCalledWith("/applications/app-1/borrowers");
  });
});
