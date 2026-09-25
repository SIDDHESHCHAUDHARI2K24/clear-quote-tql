"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";

import { fetchApplicationSummary } from "./api";
import type { ApplicationSummary } from "./api";
import { isPipelineStageTerminal } from "./pipeline";

const POLL_INTERVAL_MS = 3000;

export type WorkspaceState =
  | { kind: "loading" }
  | { kind: "not-found" }
  | { kind: "error" }
  | { kind: "ready"; summary: ApplicationSummary };

export interface WorkspaceContextValue {
  applicationId: string;
  state: WorkspaceState;
  refetch: () => Promise<void>;
}

const WorkspaceContext = createContext<WorkspaceContextValue | null>(null);

export interface WorkspaceProviderProps {
  applicationId: string;
  children: ReactNode;
}

// Fetches `GET /applications/{id}/summary` once on mount, then polls every
// 3s (spec.md AC7) while `last_pipeline_stage` is non-terminal, stopping
// once it lands on a terminal value. 404 (Decision #11/D6 -- never 403)
// surfaces as its own state so the route can render the "not found or no
// access" page instead of an empty/broken workspace.
export function WorkspaceProvider({ applicationId, children }: WorkspaceProviderProps) {
  const [state, setState] = useState<WorkspaceState>({ kind: "loading" });

  const refetch = useCallback(async () => {
    const { data, response } = await fetchApplicationSummary(applicationId);
    if (data) {
      setState({ kind: "ready", summary: data });
      return;
    }
    if (response.status === 404) {
      setState({ kind: "not-found" });
      return;
    }
    setState({ kind: "error" });
  }, [applicationId]);

  useEffect(() => {
    setState({ kind: "loading" });
    refetch();
    // `refetch` is stable for a given `applicationId` (its only
    // dependency), so this only re-runs when the route's id actually
    // changes -- intentionally not depending on `refetch` itself to avoid
    // an eslint false-positive loop warning here.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [applicationId]);

  useEffect(() => {
    if (state.kind !== "ready" || isPipelineStageTerminal(state.summary.last_pipeline_stage)) {
      return;
    }
    const timer = setInterval(() => {
      refetch();
    }, POLL_INTERVAL_MS);
    return () => clearInterval(timer);
  }, [state, refetch]);

  const value = useMemo(() => ({ applicationId, state, refetch }), [applicationId, state, refetch]);

  return <WorkspaceContext.Provider value={value}>{children}</WorkspaceContext.Provider>;
}

export function useWorkspace(): WorkspaceContextValue {
  const context = useContext(WorkspaceContext);
  if (context === null) {
    throw new Error("useWorkspace must be used within a WorkspaceProvider");
  }
  return context;
}
