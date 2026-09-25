"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { Button } from "@cq/ui";
import type { components } from "@cq/api-client";

import { applicationStatusLabel } from "../features/auth";
import { api } from "../lib/api-client";

type BorrowerMe = components["schemas"]["BorrowerMeOut"];

type SessionState = { kind: "loading" } | { kind: "signed-in"; me: BorrowerMe };

// Placeholder signed-in home (CQ-031 replaces this with the real
// home/status page). `src/middleware.ts` already redirects here-to-/login
// when the session cookie is missing; this page's own /me call is the
// second, authoritative check — a present-but-expired/revoked cookie only
// middleware can't see.
export default function Home() {
  const router = useRouter();
  const [state, setState] = useState<SessionState>({ kind: "loading" });

  useEffect(() => {
    let cancelled = false;

    api
      .GET("/api/v1/auth/borrower/me")
      .then(({ data }) => {
        if (cancelled) return;
        if (data) {
          setState({ kind: "signed-in", me: data });
          return;
        }
        // A present-but-no-longer-valid cookie (expired/revoked session):
        // middleware only checks presence, so without clearing it here
        // first, redirecting to /login would immediately bounce back to
        // / (middleware sees the stale cookie and redirects away from
        // /login). Logout deletes the (already-dead) Valkey session, a
        // no-op, and clears the cookie either way.
        api
          .POST("/api/v1/auth/borrower/logout")
          .catch(() => {})
          .finally(() => {
            if (!cancelled) router.replace("/login");
          });
      })
      .catch(() => {
        if (!cancelled) router.replace("/login");
      });

    return () => {
      cancelled = true;
    };
    // Mount-only: this checks the session once when the page loads.
    // `router` (from next/navigation's useRouter) is stable in the real
    // app, but including it here isn't needed — router.replace is only
    // ever called from callbacks, not read reactively.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function handleLogout() {
    // Best-effort: even if the request fails (network blip, API down),
    // the user's intent is to leave — don't strand them on this page with
    // no way out. Any un-cleared cookie is caught by the next /me check.
    try {
      await api.POST("/api/v1/auth/borrower/logout");
    } catch {
      // ignore — still navigate away below
    }
    router.replace("/login");
  }

  return (
    <main className="flex min-h-screen flex-col items-center justify-center gap-4 p-8">
      <h1 className="text-2xl font-semibold text-navy-900">Clear Quote</h1>
      <p role="status">
        {state.kind === "loading" ? "Checking session…" : `Hi ${state.me.first_name}`}
      </p>
      {state.kind === "signed-in" && (
        <>
          <p className="text-neutral-600">
            {state.me.latest_application
              ? applicationStatusLabel(state.me.latest_application.status)
              : "No application yet"}
          </p>
          <Button variant="secondary" onClick={handleLogout}>
            Logout
          </Button>
        </>
      )}
    </main>
  );
}
