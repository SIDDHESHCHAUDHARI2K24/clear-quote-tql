import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const { getMock } = vi.hoisted(() => ({ getMock: vi.fn() }));

vi.mock("@cq/api-client", () => ({
  createApiClient: () => ({
    GET: getMock,
    PUT: vi.fn(),
    POST: vi.fn(),
    PATCH: vi.fn(),
    DELETE: vi.fn(),
  }),
}));

import { ToastProvider } from "@cq/ui";

import { makeSummary } from "../../workspace/test-fixtures";
import { WorkspaceProvider } from "../../workspace";
import { makeSection } from "./test-fixtures";
import { useSection } from "./useSection";
import type { SectionResponse } from "./api";

const APPLICATION_ID = "11111111-1111-1111-1111-111111111111";
const SUMMARY = makeSummary();

function Probe({ applied }: { applied?: SectionResponse }) {
  const { state, applyResult } = useSection(APPLICATION_ID, "borrowers");
  if (state.kind !== "ready") return <span>{state.kind}</span>;
  return (
    <div>
      <span>flags:{state.section.flags.length}</span>
      <button onClick={() => applyResult(applied ?? makeSection())}>apply</button>
    </div>
  );
}

describe("useSection (docs/backlog/CQ-028-verification-tabs)", () => {
  afterEach(() => {
    getMock.mockReset();
  });

  it("loads the tab's section from GET /sections/{tab} on mount", async () => {
    getMock.mockImplementation((path: string) =>
      Promise.resolve({ data: path.includes("/summary") ? SUMMARY : makeSection() }),
    );

    render(
      <ToastProvider>
        <WorkspaceProvider applicationId={APPLICATION_ID}>
          <Probe />
        </WorkspaceProvider>
      </ToastProvider>,
    );

    await act(async () => {
      await Promise.resolve();
    });
    expect(screen.getByText("flags:0")).toBeInTheDocument();
  });

  it("applyResult refreshes the workspace summary (tab-rail badge) and shows the resumed toast when resume.requested is true", async () => {
    getMock.mockImplementation((path: string) =>
      Promise.resolve({ data: path.includes("/summary") ? SUMMARY : makeSection() }),
    );

    render(
      <ToastProvider>
        <WorkspaceProvider applicationId={APPLICATION_ID}>
          <Probe applied={makeSection({ resume: { requested: true, reason: "resumed" } })} />
        </WorkspaceProvider>
      </ToastProvider>,
    );
    await act(async () => {
      await Promise.resolve();
    });

    const summaryCallsBefore = getMock.mock.calls.filter(([path]) =>
      String(path).includes("/summary"),
    ).length;

    await act(async () => {
      fireEvent.click(screen.getByText("apply"));
      await Promise.resolve();
    });

    expect(await screen.findByText("All checks pass — pricing resumed")).toBeInTheDocument();
    const summaryCallsAfter = getMock.mock.calls.filter(([path]) =>
      String(path).includes("/summary"),
    ).length;
    expect(summaryCallsAfter).toBeGreaterThan(summaryCallsBefore);
  });

  it("bridges the polling race: a resumed edit's own refetch can still see last_pipeline_stage=null (a fresh run's first activity hasn't committed yet), so it schedules delayed refetches instead of leaving WorkspaceProvider's polling never-started", async () => {
    vi.useFakeTimers();
    try {
      // Every /summary call returns `last_pipeline_stage: null` -- exactly
      // the state that made WorkspaceProvider's own polling loop never
      // start in the real bug this test guards (see useSection.ts's
      // RESUME_BRIDGE_DELAYS_MS comment).
      getMock.mockImplementation((path: string) =>
        Promise.resolve({
          data: path.includes("/summary") ? SUMMARY : makeSection(),
        }),
      );

      render(
        <ToastProvider>
          <WorkspaceProvider applicationId={APPLICATION_ID}>
            <Probe applied={makeSection({ resume: { requested: true, reason: "started" } })} />
          </WorkspaceProvider>
        </ToastProvider>,
      );
      await act(async () => {
        await Promise.resolve();
      });

      const summaryCalls = () =>
        getMock.mock.calls.filter(([path]) => String(path).includes("/summary")).length;
      const callsBeforeApply = summaryCalls();

      await act(async () => {
        fireEvent.click(screen.getByText("apply"));
        await Promise.resolve();
      });
      // applyResult's own immediate refetchWorkspace() call.
      expect(summaryCalls()).toBe(callsBeforeApply + 1);

      await act(async () => {
        await vi.advanceTimersByTimeAsync(1500);
      });
      expect(summaryCalls()).toBe(callsBeforeApply + 2);

      await act(async () => {
        await vi.advanceTimersByTimeAsync(2500); // -> 4000ms total
      });
      expect(summaryCalls()).toBe(callsBeforeApply + 3);

      await act(async () => {
        await vi.advanceTimersByTimeAsync(4000); // -> 8000ms total
      });
      expect(summaryCalls()).toBe(callsBeforeApply + 4);
    } finally {
      vi.useRealTimers();
    }
  });

  it("does not toast when resume.requested is false (blocking flags remain)", async () => {
    getMock.mockImplementation((path: string) =>
      Promise.resolve({ data: path.includes("/summary") ? SUMMARY : makeSection() }),
    );

    render(
      <ToastProvider>
        <WorkspaceProvider applicationId={APPLICATION_ID}>
          <Probe
            applied={makeSection({ resume: { requested: false, reason: "blocking_flags_remain" } })}
          />
        </WorkspaceProvider>
      </ToastProvider>,
    );
    await act(async () => {
      await Promise.resolve();
    });

    await act(async () => {
      fireEvent.click(screen.getByText("apply"));
      await Promise.resolve();
    });

    expect(screen.queryByText("All checks pass — pricing resumed")).not.toBeInTheDocument();
  });
});
