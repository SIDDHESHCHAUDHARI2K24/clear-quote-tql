import { act, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const { getMock } = vi.hoisted(() => ({ getMock: vi.fn() }));

vi.mock("@cq/api-client", () => ({
  createApiClient: () => ({ GET: getMock, PATCH: vi.fn() }),
}));

import { makeSummary } from "./test-fixtures";
import { useWorkspace, WorkspaceProvider } from "./WorkspaceProvider";

const APPLICATION_ID = "11111111-1111-1111-1111-111111111111";

function Probe() {
  const { state } = useWorkspace();
  if (state.kind !== "ready") return <span>{state.kind}</span>;
  return <span>stage:{state.summary.last_pipeline_stage ?? "null"}</span>;
}

describe("WorkspaceProvider polling (spec.md AC7)", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    getMock.mockReset();
    vi.useRealTimers();
  });

  it("404s into a not-found state without polling", async () => {
    getMock.mockResolvedValueOnce({ data: undefined, response: { status: 404 } });

    render(
      <WorkspaceProvider applicationId={APPLICATION_ID}>
        <Probe />
      </WorkspaceProvider>,
    );

    await act(async () => {
      await Promise.resolve();
    });
    expect(screen.getByText("not-found")).toBeInTheDocument();
  });

  it("code-review fix: a rejected fetch (network failure) settles into an error state, not stuck loading forever", async () => {
    getMock.mockRejectedValueOnce(new TypeError("Failed to fetch"));

    render(
      <WorkspaceProvider applicationId={APPLICATION_ID}>
        <Probe />
      </WorkspaceProvider>,
    );

    await act(async () => {
      await Promise.resolve();
    });
    expect(screen.getByText("error")).toBeInTheDocument();
  });

  it("polls every 3s while the stage is non-terminal, and stops once terminal", async () => {
    getMock
      .mockResolvedValueOnce({
        data: makeSummary({ last_pipeline_stage: "verifying" }),
        response: { status: 200 },
      })
      .mockResolvedValueOnce({
        data: makeSummary({ last_pipeline_stage: "enriching" }),
        response: { status: 200 },
      })
      .mockResolvedValueOnce({
        data: makeSummary({ last_pipeline_stage: "priced" }),
        response: { status: 200 },
      });

    render(
      <WorkspaceProvider applicationId={APPLICATION_ID}>
        <Probe />
      </WorkspaceProvider>,
    );

    await act(async () => {
      await Promise.resolve();
    });
    expect(screen.getByText("stage:verifying")).toBeInTheDocument();
    expect(getMock).toHaveBeenCalledTimes(1);

    await act(async () => {
      vi.advanceTimersByTime(3000);
      await Promise.resolve();
    });
    expect(screen.getByText("stage:enriching")).toBeInTheDocument();
    expect(getMock).toHaveBeenCalledTimes(2);

    await act(async () => {
      vi.advanceTimersByTime(3000);
      await Promise.resolve();
    });
    expect(screen.getByText("stage:priced")).toBeInTheDocument();
    expect(getMock).toHaveBeenCalledTimes(3);

    // Terminal now -- no further polling.
    await act(async () => {
      vi.advanceTimersByTime(10000);
      await Promise.resolve();
    });
    expect(getMock).toHaveBeenCalledTimes(3);
  });
});
