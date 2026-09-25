"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { useToast } from "@cq/ui";

import { useWorkspace } from "../../workspace";
import { fetchSection } from "./api";
import type { SectionResponse, SectionTab } from "./api";

export type SectionState =
  { kind: "loading" } | { kind: "error" } | { kind: "ready"; section: SectionResponse };

export interface UseSectionResult {
  state: SectionState;
  /** Re-fetches this tab's section from the API (e.g. after a failed save). */
  refetch: () => Promise<void>;
  /** Adopts a `SectionResponse` a write endpoint already returned: sets this
   * tab's state directly (no extra `GET`), refreshes the CQ-016 workspace
   * summary so the tab-rail badge and header re-render (spec.md "Shared
   * pieces"), and shows the "pricing resumed" toast when `resume.requested`
   * is true -- the backend only sets that once the last blocking flag has
   * cleared (plan.md #8), so no extra flag-counting is needed here. */
  applyResult: (section: SectionResponse) => void;
}

const RESUMED_TOAST = "All checks pass — pricing resumed";

// A `resume.requested` edit races the CQ-016 header: `WorkspaceProvider`
// only keeps polling `.../summary` while `last_pipeline_stage` is non-null
// (a fresh, just-started run -- Aisha/Ben-style seeded applications with no
// prior Temporal run, plan.md #9 -- reports `null` until its first activity
// commits, a few hundred ms to ~1s later). `applyResult`'s own immediate
// `refetchWorkspace()` call almost always lands before that, sees `null`,
// and `isPipelineStageTerminal(null)` reads that as "nothing to poll for"
// (see workspace/WorkspaceProvider.tsx's own comment) -- so polling never
// starts and the header stays on "Needs attention" until a manual reload,
// even though the pipeline finishes seconds later. These extra delayed
// refetches bridge that gap; once one of them observes a non-null stage,
// `WorkspaceProvider`'s own 3s interval takes over from there.
const RESUME_BRIDGE_DELAYS_MS = [1500, 4000, 8000];

export function useSection(applicationId: string, tab: SectionTab): UseSectionResult {
  const [state, setState] = useState<SectionState>({ kind: "loading" });
  const { refetch: refetchWorkspace } = useWorkspace();
  const toast = useToast();
  const bridgeTimers = useRef<ReturnType<typeof setTimeout>[]>([]);

  useEffect(
    () => () => {
      bridgeTimers.current.forEach(clearTimeout);
    },
    [],
  );

  const load = useCallback(async () => {
    try {
      const { data, error } = await fetchSection(applicationId, tab);
      if (data) {
        setState({ kind: "ready", section: data });
        return;
      }
      void error;
      setState({ kind: "error" });
    } catch {
      setState({ kind: "error" });
    }
  }, [applicationId, tab]);

  useEffect(() => {
    setState({ kind: "loading" });
    void load();
  }, [load]);

  const applyResult = useCallback(
    (section: SectionResponse) => {
      setState({ kind: "ready", section });
      void refetchWorkspace();
      if (section.resume?.requested) {
        toast.show(RESUMED_TOAST, { tone: "success" });
        bridgeTimers.current.forEach(clearTimeout);
        bridgeTimers.current = RESUME_BRIDGE_DELAYS_MS.map((delay) =>
          setTimeout(() => void refetchWorkspace(), delay),
        );
      }
    },
    [refetchWorkspace, toast],
  );

  return { state, refetch: load, applyResult };
}
