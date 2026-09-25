import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const { getMock, replaceMock, searchParamsGet } = vi.hoisted(() => ({
  getMock: vi.fn(),
  replaceMock: vi.fn(),
  searchParamsGet: vi.fn(() => null),
}));

vi.mock("@cq/api-client", () => ({
  createApiClient: () => ({ GET: getMock, POST: vi.fn() }),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: replaceMock }),
  useSearchParams: () => ({ get: searchParamsGet, toString: () => "" }),
}));

import { DashboardPage } from "./DashboardPage";

function ok(data: unknown) {
  return { data, response: { status: 200 } };
}

const EMPTY_TILES = {
  clients: 3,
  applications: 4,
  pre_approvals_sent: 1,
  with_property: 2,
  awaiting_review: 1,
  needs_attention: 1,
  stale_quotes: 0,
};

function dashboardBody(overrides: Record<string, unknown> = {}) {
  return {
    tiles: EMPTY_TILES,
    attention: [],
    stale: [],
    activity: [],
    los: null,
    ...overrides,
  };
}

describe("DashboardPage", () => {
  beforeEach(() => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
  });

  afterEach(() => {
    getMock.mockReset();
    replaceMock.mockReset();
    searchParamsGet.mockReset();
    searchParamsGet.mockReturnValue(null);
    vi.useRealTimers();
  });

  it("shows a loading state before the fetch resolves", () => {
    getMock.mockReturnValue(new Promise(() => {})); // never resolves
    render(<DashboardPage />);
    expect(screen.getByRole("status", { name: "Loading dashboard" })).toBeInTheDocument();
  });

  it("renders tiles and the empty-state lists once loaded", async () => {
    getMock.mockResolvedValueOnce(ok(dashboardBody()));
    render(<DashboardPage />);

    expect(await screen.findByRole("heading", { level: 1, name: "Dashboard" })).toBeInTheDocument();
    expect(screen.getByText("3")).toBeInTheDocument(); // clients tile count
    expect(screen.getAllByText("Nothing needs you right now")).toHaveLength(3);
  });

  it("shows an error state with a working retry on a rejected fetch", async () => {
    getMock.mockRejectedValueOnce(new TypeError("Failed to fetch"));
    render(<DashboardPage />);

    expect(await screen.findByText("Couldn't load the dashboard")).toBeInTheDocument();

    getMock.mockResolvedValueOnce(ok(dashboardBody()));
    await userEvent
      .setup({ advanceTimers: vi.advanceTimersByTime })
      .click(screen.getByRole("button", { name: "Retry" }));

    expect(await screen.findByRole("heading", { level: 1, name: "Dashboard" })).toBeInTheDocument();
  });

  it("shows no LO filter for an LO (los: null)", async () => {
    getMock.mockResolvedValueOnce(ok(dashboardBody({ los: null })));
    render(<DashboardPage />);
    await screen.findByRole("heading", { level: 1, name: "Dashboard" });
    expect(screen.queryByLabelText("Loan officer")).not.toBeInTheDocument();
  });

  it("shows the LO filter for a Manager/Admin and pushes the choice into the URL", async () => {
    getMock.mockResolvedValueOnce(
      ok(
        dashboardBody({
          los: [
            { id: "lo-1", full_name: "Jordan Lee" },
            { id: "lo-2", full_name: "Riley Admin" },
          ],
        }),
      ),
    );
    render(<DashboardPage />);
    const select = await screen.findByLabelText("Loan officer");

    getMock.mockResolvedValueOnce(ok(dashboardBody()));
    await userEvent
      .setup({ advanceTimers: vi.advanceTimersByTime })
      .selectOptions(select, "Jordan Lee");

    expect(replaceMock).toHaveBeenCalledWith("/?lo_id=lo-1");
  });

  it("refreshes every 30s while the tab is visible", async () => {
    getMock.mockResolvedValue(ok(dashboardBody()));
    render(<DashboardPage />);
    await screen.findByRole("heading", { level: 1, name: "Dashboard" });

    expect(getMock).toHaveBeenCalledTimes(1);
    await act(async () => {
      vi.advanceTimersByTime(30_000);
    });
    await waitFor(() => expect(getMock).toHaveBeenCalledTimes(2));
  });

  it("does not refresh on the 30s tick while the tab is hidden", async () => {
    getMock.mockResolvedValue(ok(dashboardBody()));
    render(<DashboardPage />);
    await screen.findByRole("heading", { level: 1, name: "Dashboard" });
    expect(getMock).toHaveBeenCalledTimes(1);

    Object.defineProperty(document, "visibilityState", {
      configurable: true,
      get: () => "hidden",
    });
    await act(async () => {
      vi.advanceTimersByTime(30_000);
    });
    expect(getMock).toHaveBeenCalledTimes(1);

    Object.defineProperty(document, "visibilityState", {
      configurable: true,
      get: () => "visible",
    });
  });

  it("code-review fix: a failed poll refresh keeps showing the last loaded dashboard instead of blanking it out", async () => {
    getMock.mockResolvedValueOnce(ok(dashboardBody()));
    render(<DashboardPage />);
    await screen.findByRole("heading", { level: 1, name: "Dashboard" });

    getMock.mockRejectedValueOnce(new TypeError("Failed to fetch"));
    await act(async () => {
      vi.advanceTimersByTime(30_000);
    });

    // Still showing the dashboard (not the full-page error screen), plus a
    // small "couldn't refresh" notice -- the tiles/lists are not wiped.
    expect(screen.getByRole("heading", { level: 1, name: "Dashboard" })).toBeInTheDocument();
    expect(await screen.findByText(/Couldn't refresh/)).toBeInTheDocument();
    expect(screen.queryByText("Couldn't load the dashboard")).not.toBeInTheDocument();

    // A subsequent successful refresh clears the notice again.
    getMock.mockResolvedValueOnce(ok(dashboardBody()));
    await act(async () => {
      vi.advanceTimersByTime(30_000);
    });
    await waitFor(() => expect(screen.queryByText(/Couldn't refresh/)).not.toBeInTheDocument());
  });
});
