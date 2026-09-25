"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";

import type { DashboardResponse } from "./api";
import { fetchDashboard } from "./api";
import { ActivityFeed } from "./ActivityFeed";
import { AttentionList } from "./AttentionList";
import { LoFilter } from "./LoFilter";
import { StaleList } from "./StaleList";
import { Tiles } from "./Tiles";

const POLL_INTERVAL_MS = 30_000;

type LoadState =
  | { kind: "loading" }
  | { kind: "ready"; data: DashboardResponse; refreshFailed: boolean }
  | { kind: "error" };

/**
 * `/` -- the LO console landing page (CQ-025 spec.md). Loads
 * `GET /api/v1/dashboard`, keeps the Manager/Admin LO filter in the URL
 * (`?lo_id=`, read via `useSearchParams` -- the route's `Suspense`
 * boundary, `(staff)/page.tsx`, follows the borrower portal's report page
 * precedent), and refreshes every 30s while the tab is visible.
 */
export function DashboardPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const loId = searchParams.get("lo_id");
  const [state, setState] = useState<LoadState>({ kind: "loading" });
  const mountedRef = useRef(true);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

  // code-review (CQ-025): a poll tick (or an lo filter change) that fails
  // transiently must not blank out an already-rendered dashboard -- only
  // the *first* load (no data yet) shows the full error screen. A later
  // failure keeps showing the last good `data` and flips `refreshFailed`
  // instead, so a network blip during the 30s poll doesn't read as "sign
  // out" or wipe the tiles/lists the LO was just looking at.
  const load = useCallback(async () => {
    try {
      const { data } = await fetchDashboard(loId ?? undefined);
      if (!mountedRef.current) return;
      if (data) {
        setState({ kind: "ready", data, refreshFailed: false });
      } else {
        setState((prev) =>
          prev.kind === "ready" ? { ...prev, refreshFailed: true } : { kind: "error" },
        );
      }
    } catch {
      if (!mountedRef.current) return;
      setState((prev) =>
        prev.kind === "ready" ? { ...prev, refreshFailed: true } : { kind: "error" },
      );
    }
  }, [loId]);

  useEffect(() => {
    setState({ kind: "loading" });
    void load();
  }, [load]);

  useEffect(() => {
    const interval = setInterval(() => {
      if (document.visibilityState === "visible") void load();
    }, POLL_INTERVAL_MS);
    const onVisibilityChange = () => {
      if (document.visibilityState === "visible") void load();
    };
    document.addEventListener("visibilitychange", onVisibilityChange);
    return () => {
      clearInterval(interval);
      document.removeEventListener("visibilitychange", onVisibilityChange);
    };
  }, [load]);

  const handleLoChange = useCallback(
    (nextLoId: string | null) => {
      const params = new URLSearchParams(searchParams.toString());
      if (nextLoId) {
        params.set("lo_id", nextLoId);
      } else {
        params.delete("lo_id");
      }
      const query = params.toString();
      router.replace(query ? `/?${query}` : "/");
    },
    [router, searchParams],
  );

  if (state.kind === "loading") {
    return (
      <div
        role="status"
        aria-label="Loading dashboard"
        className="animate-pulse p-6"
        data-testid="dashboard-loading"
      >
        <div className="mb-4 h-8 w-64 rounded bg-neutral-200" />
        <div className="h-40 rounded bg-neutral-100" />
      </div>
    );
  }

  if (state.kind === "error") {
    return (
      <div className="flex flex-col items-center gap-3 px-6 py-16 text-center">
        <h1 className="text-lg font-semibold text-navy-900">Couldn&apos;t load the dashboard</h1>
        <p className="max-w-md text-sm text-neutral-600">Something went wrong. Try again.</p>
        <button
          type="button"
          onClick={() => void load()}
          className="text-sm font-medium text-navy-500 hover:underline"
        >
          Retry
        </button>
      </div>
    );
  }

  const { data, refreshFailed } = state;

  return (
    <div className="flex flex-col gap-6 p-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <h1 className="text-lg font-semibold text-navy-900">Dashboard</h1>
        {data.los && <LoFilter los={data.los} value={loId} onChange={handleLoChange} />}
      </div>
      {refreshFailed && (
        <p role="status" className="text-sm text-status-warning">
          Couldn&apos;t refresh -- showing the last loaded numbers.
        </p>
      )}
      <Tiles tiles={data.tiles} loId={loId} />
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <AttentionList items={data.attention} />
        <StaleList items={data.stale} />
        <ActivityFeed items={data.activity} />
      </div>
    </div>
  );
}
