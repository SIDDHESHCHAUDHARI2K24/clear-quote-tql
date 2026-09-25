"use client";

import { useEffect, useState } from "react";

import { Button, extractErrorMessage } from "@cq/ui";

import { STALE_CHECK_JOB_AVAILABLE, fetchIntegrations, putIntegrationForceFailure } from "./api";
import type { AdapterStatus } from "./api";

function formatCalledAt(at: string | null): string {
  if (!at) return "Never called";
  // Pinned locale (not the runtime default -- react-doctor's
  // no-locale-format-in-render): matches packages/ui/report/format.ts's
  // own convention, so server and client always render the same string.
  return new Date(at).toLocaleString("en-US", {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
    second: "2-digit",
  });
}

type LoadState =
  | { kind: "loading" }
  | { kind: "error"; message: string }
  | { kind: "ready"; adapters: AdapterStatus[] };

/** spec.md CQ-029 "Integration panel" (Admin only): a status row per
 * adapter with the force-failure toggle (AC4/AC5), and a banner while any
 * failure is forced. */
export function IntegrationsPanel() {
  const [state, setState] = useState<LoadState>({ kind: "loading" });
  const [pendingAdapter, setPendingAdapter] = useState<string | null>(null);

  function load() {
    setState({ kind: "loading" });
    fetchIntegrations().then(({ data, error }) => {
      if (error || !data) {
        setState({
          kind: "error",
          message: extractErrorMessage(error, "Couldn't load the integration panel. Try again."),
        });
        return;
      }
      setState({ kind: "ready", adapters: data.adapters });
    });
  }

  useEffect(load, []);

  function applyAdapterUpdate(adapter: string, forceFailure: boolean) {
    setState((current) =>
      current.kind === "ready"
        ? {
            kind: "ready",
            adapters: current.adapters.map((row) =>
              row.adapter === adapter ? { ...row, force_failure: forceFailure } : row,
            ),
          }
        : current,
    );
  }

  async function toggle(adapter: string, nextValue: boolean) {
    setPendingAdapter(adapter);
    // Optimistic update: a controlled checkbox otherwise snaps back to its
    // old `checked` value the instant this re-render (from `setPendingAdapter`)
    // lands, before the PUT resolves.
    applyAdapterUpdate(adapter, nextValue);
    // Code review finding: without try/finally, a rejected promise (a
    // network drop, not just an `{error}` response) would skip both
    // clearing `pendingAdapter` and reverting the optimistic update,
    // leaving the checkbox stuck disabled and possibly showing a state
    // Valkey never actually reached.
    try {
      const { data, error } = await putIntegrationForceFailure(adapter, nextValue);
      if (error || !data) {
        applyAdapterUpdate(adapter, !nextValue);
        return;
      }
      setState((current) =>
        current.kind === "ready"
          ? {
              kind: "ready",
              adapters: current.adapters.map((row) => (row.adapter === adapter ? data : row)),
            }
          : current,
      );
    } catch {
      applyAdapterUpdate(adapter, !nextValue);
    } finally {
      setPendingAdapter(null);
    }
  }

  if (state.kind === "loading") {
    return (
      <p role="status" className="text-sm text-neutral-600">
        Loading integrations…
      </p>
    );
  }

  if (state.kind === "error") {
    return (
      <p role="alert" className="text-sm text-status-danger">
        {state.message}
      </p>
    );
  }

  const anyForced = state.adapters.some((row) => row.force_failure);

  return (
    <div className="flex flex-col gap-4">
      {anyForced && (
        <div
          role="alert"
          className="rounded-md bg-status-warning/10 px-3 py-2 text-sm font-medium text-status-warning"
        >
          At least one integration is forced to fail. The pipeline will surface that error until
          it&apos;s turned back off.
        </div>
      )}

      {STALE_CHECK_JOB_AVAILABLE && (
        <div>
          <Button variant="secondary">Run stale check now</Button>
        </div>
      )}

      <table className="w-full border-collapse text-sm">
        <thead>
          <tr className="border-b border-neutral-200 text-left text-neutral-600">
            <th scope="col" className="px-3 py-2 font-medium">
              Adapter
            </th>
            <th scope="col" className="px-3 py-2 font-medium">
              Provider
            </th>
            <th scope="col" className="px-3 py-2 font-medium">
              Last call
            </th>
            <th scope="col" className="px-3 py-2 font-medium">
              Latency
            </th>
            <th scope="col" className="px-3 py-2 font-medium">
              Result
            </th>
            <th scope="col" className="px-3 py-2 font-medium">
              Calls (1h)
            </th>
            <th scope="col" className="px-3 py-2 font-medium">
              Force failure
            </th>
          </tr>
        </thead>
        <tbody>
          {state.adapters.map((row) => (
            <tr key={row.adapter} className="border-b border-neutral-100">
              <td className="px-3 py-2 font-medium text-navy-900">{row.adapter}</td>
              <td className="px-3 py-2 text-neutral-600">{row.provider}</td>
              <td className="px-3 py-2 text-neutral-600">{formatCalledAt(row.last_call_at)}</td>
              <td className="px-3 py-2 text-neutral-600">
                {row.last_latency_ms !== null ? `${row.last_latency_ms} ms` : "—"}
              </td>
              <td
                className={
                  row.last_result === "ok"
                    ? "px-3 py-2 text-status-success"
                    : row.last_result === "never_called"
                      ? "px-3 py-2 text-neutral-400"
                      : "px-3 py-2 text-status-danger"
                }
              >
                {row.last_result}
              </td>
              <td className="px-3 py-2 text-neutral-600">{row.calls_last_hour}</td>
              <td className="px-3 py-2">
                <label className="flex items-center gap-2">
                  <input
                    type="checkbox"
                    checked={row.force_failure}
                    disabled={pendingAdapter === row.adapter}
                    onChange={(event) => toggle(row.adapter, event.target.checked)}
                    aria-label={`Force ${row.adapter} to fail`}
                  />
                  <span className="text-xs text-neutral-600">
                    {row.force_failure ? "Forced to fail" : "Normal"}
                  </span>
                </label>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
