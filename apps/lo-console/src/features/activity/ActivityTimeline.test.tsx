// Code review regression test (day bucketing must use the viewer's local
// calendar date, not UTC): pinned so the test is deterministic regardless
// of the machine's own zone. America/New_York (UTC-4/-5) is chosen because
// it reproduces the bug this guards against -- for zones where local
// midnight falls close to UTC midnight, the same test wouldn't have caught
// the original bug.
process.env.TZ = "America/New_York";

import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const { getMock } = vi.hoisted(() => ({ getMock: vi.fn() }));

vi.mock("@cq/api-client", () => ({
  createApiClient: () => ({ GET: getMock }),
}));

import { ActivityTimeline } from "./ActivityTimeline";
import type { ActivityEvent } from "./api";

const APPLICATION_ID = "11111111-1111-1111-1111-111111111111";

function event(overrides: Partial<ActivityEvent> = {}): ActivityEvent {
  return {
    id: crypto.randomUUID(),
    actor: { kind: "system", name: "System" },
    type: "pipeline.imported",
    message: "Imported from the LOS",
    payload_summary: null,
    at: new Date().toISOString(),
    ...overrides,
  };
}

describe("ActivityTimeline (AC1)", () => {
  afterEach(() => {
    getMock.mockReset();
  });

  describe("day grouping (code review regression: local date, not UTC)", () => {
    beforeEach(() => {
      // "Now": Sep 25, 9 PM America/New_York (UTC-4) == Sep 26, 1 AM UTC.
      // `shouldAdvanceTime` keeps the fake clock ticking in step with real
      // time so `findByText`'s own setTimeout-based polling still works.
      vi.useFakeTimers({ shouldAdvanceTime: true });
      vi.setSystemTime(new Date("2026-09-26T01:00:00.000Z"));
    });

    afterEach(() => {
      vi.useRealTimers();
    });

    it("groups an event from earlier the same local evening under Today, even though its UTC date differs from 'now'’s UTC date", async () => {
      getMock.mockResolvedValueOnce({
        data: {
          // Sep 25, 7 PM America/New_York == Sep 25, 11 PM UTC -- same
          // local day as "now" above, but a different UTC calendar day.
          items: [event({ at: "2026-09-25T23:00:00.000Z", message: "Enriched pricing inputs" })],
          total: 1,
          page: 1,
          page_size: 25,
        },
        response: { status: 200 },
      });

      render(<ActivityTimeline applicationId={APPLICATION_ID} />);

      expect(await screen.findByText("Today")).toBeInTheDocument();
      expect(screen.queryByText("September 25, 2026")).not.toBeInTheDocument();
    });
  });

  it("shows events grouped by day, newest first, with readable messages", async () => {
    getMock.mockResolvedValueOnce({
      data: {
        items: [
          event({ type: "pipeline.priced", message: "Drafted 3 quotes" }),
          event({ type: "pipeline.verified", message: "Passed verification" }),
        ],
        total: 2,
        page: 1,
        page_size: 25,
      },
      response: { status: 200 },
    });

    render(<ActivityTimeline applicationId={APPLICATION_ID} />);

    expect(await screen.findByText("Drafted 3 quotes")).toBeInTheDocument();
    expect(screen.getByText("Passed verification")).toBeInTheDocument();
    expect(getMock).toHaveBeenCalledWith(
      "/api/v1/applications/{application_id}/activity",
      expect.objectContaining({
        params: { path: { application_id: APPLICATION_ID }, query: { page: 1 } },
      }),
    );
  });

  it("styles system events quieter than a borrower's own action", async () => {
    getMock.mockResolvedValueOnce({
      data: {
        items: [
          event({
            type: "quote.move_forward",
            message: "Asked to move forward with the selected quote",
            actor: { kind: "borrower", name: "Marcus Hale" },
          }),
          event({ type: "pipeline.imported", message: "Imported from the LOS" }),
        ],
        total: 2,
        page: 1,
        page_size: 25,
      },
      response: { status: 200 },
    });

    render(<ActivityTimeline applicationId={APPLICATION_ID} />);
    await waitFor(() => expect(getMock).toHaveBeenCalledTimes(1));

    const borrowerRow = screen.getByText("Asked to move forward with the selected quote");
    const systemRow = screen.getByText("Imported from the LOS");

    expect(borrowerRow.className).toContain("font-medium");
    expect(systemRow.className).toContain("font-normal");
    expect(screen.getByText(/Marcus Hale/)).toBeInTheDocument();
    expect(screen.getByText(/System/)).toBeInTheDocument();
  });

  it("shows an empty state with no events", async () => {
    getMock.mockResolvedValueOnce({
      data: { items: [], total: 0, page: 1, page_size: 25 },
      response: { status: 200 },
    });

    render(<ActivityTimeline applicationId={APPLICATION_ID} />);

    expect(await screen.findByText("No activity yet")).toBeInTheDocument();
  });

  it("shows an error message when the fetch fails", async () => {
    getMock.mockResolvedValueOnce({
      data: undefined,
      error: { error: { code: "NOT_FOUND", message: "Application not found" } },
      response: { status: 404 },
    });

    render(<ActivityTimeline applicationId={APPLICATION_ID} />);

    expect(await screen.findByRole("alert")).toHaveTextContent("Application not found");
  });
});
