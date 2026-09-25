"use client";

import { useEffect, useState } from "react";

import { api } from "../lib/api-client";

type HealthState =
  | { kind: "loading" }
  | { kind: "ok" }
  | { kind: "degraded"; failingChecks: string[] }
  | { kind: "unreachable" };

// The /health OpenAPI contract (CQ-004) only documents a 200 response; the
// same HealthReport body is also returned on 503 ("degraded"). openapi-fetch
// resolves (never rejects) on a non-2xx HTTP status, and — because 503 isn't
// a documented response — puts that body under `error`, not `data`. So we
// read the report from whichever of `data`/`error` is present, and only
// treat a network-level failure (a rejected promise) as "unreachable".
function isHealthReport(
  value: unknown,
): value is { status: "ok" | "degraded"; checks: Record<string, string> } {
  return (
    typeof value === "object" &&
    value !== null &&
    "status" in value &&
    "checks" in value &&
    typeof (value as { checks: unknown }).checks === "object"
  );
}

export default function Home() {
  const [state, setState] = useState<HealthState>({ kind: "loading" });

  useEffect(() => {
    let cancelled = false;

    api
      .GET("/health")
      .then(({ data, error }) => {
        if (cancelled) return;
        const report = isHealthReport(data) ? data : isHealthReport(error) ? error : undefined;
        if (!report) {
          setState({ kind: "unreachable" });
        } else if (report.status === "ok") {
          setState({ kind: "ok" });
        } else {
          const failingChecks = Object.entries(report.checks)
            .filter(([, value]) => value !== "ok")
            .map(([name]) => name);
          setState({ kind: "degraded", failingChecks });
        }
      })
      .catch(() => {
        if (!cancelled) setState({ kind: "unreachable" });
      });

    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <main className="flex min-h-screen flex-col items-center justify-center gap-4 p-8">
      <h1 className="text-2xl font-semibold text-navy-900">Clear Quote — Borrower Portal</h1>
      <p
        role="status"
        className={
          state.kind === "unreachable" || state.kind === "degraded"
            ? "text-status-danger"
            : "text-status-success"
        }
      >
        {state.kind === "loading" && "Checking API…"}
        {state.kind === "ok" && "API reachable"}
        {state.kind === "degraded" &&
          `API degraded — failing checks: ${state.failingChecks.join(", ")}`}
        {state.kind === "unreachable" && "API unreachable"}
      </p>
    </main>
  );
}
