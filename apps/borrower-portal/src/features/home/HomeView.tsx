"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { Button, EmptyState } from "@cq/ui";

import { api } from "../../lib/api-client";

import { ApplicationCard } from "./ApplicationCard";
import { ConsentBanner } from "./ConsentBanner";
import type { PortalHomeResponse } from "./api";
import { fetchPortalHome } from "./api";

type ViewState =
  { kind: "loading" } | { kind: "error" } | { kind: "loaded"; home: PortalHomeResponse };

/**
 * `/` for a signed-in borrower (spec.md Home): a greeting, one card per
 * application, a task banner when any application has a pending
 * credit-check consent, and an empty state with "Start your application"
 * when there are none. Fetches `GET /api/v1/portal/me` client-side (same
 * convention as `features/report/ReportView.tsx`) so the httpOnly
 * `cq_borrower_session` cookie rides along.
 *
 * Renders only the `stage`/`label` text the backend already produced --
 * no status re-derivation here (spec.md "Notes for the agent").
 */
export function HomeView() {
  const router = useRouter();
  const [state, setState] = useState<ViewState>({ kind: "loading" });

  const load = useCallback(() => {
    setState({ kind: "loading" });
    return fetchPortalHome()
      .then(({ data, response }) => {
        if (data) {
          setState({ kind: "loaded", home: data });
          return;
        }
        if (response.status === 401) {
          // Same pattern as `BorrowerSessionProvider`/`ReportView`: clear
          // the stale cookie first, or `src/middleware.ts` (which only
          // checks the cookie's *presence*, not validity) bounces the
          // `/login` navigation straight back to `/`, re-triggering this
          // same failed fetch (review round 1 finding).
          api
            .POST("/api/v1/auth/borrower/logout")
            .catch(() => {})
            .finally(() => {
              router.replace("/login");
            });
          return;
        }
        setState({ kind: "error" });
      })
      .catch(() => {
        setState({ kind: "error" });
      });
  }, [router]);

  useEffect(() => {
    void load();
    // Mount-only: `load` depends on `router`, whose identity isn't
    // guaranteed stable across renders (same reasoning as
    // `features/report/ReportView.tsx`'s own mount-only effect).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (state.kind === "loading") {
    return (
      <main role="status" aria-live="polite" className="flex flex-col gap-4">
        <p className="text-sm text-neutral-600">Loading your home…</p>
        <div className="h-24 animate-pulse rounded-lg bg-neutral-100" aria-hidden="true" />
      </main>
    );
  }

  if (state.kind === "error") {
    return (
      <main className="flex flex-col items-center gap-3 p-8 text-center">
        <h1 className="text-xl font-semibold text-navy-900">Something went wrong</h1>
        <p className="text-neutral-600">Try reloading the page.</p>
      </main>
    );
  }

  const { home } = state;
  const pendingConsent = home.applications.find(
    (application) => application.next_action.type === "authorize_credit_check",
  );

  return (
    <main className="flex flex-col gap-6">
      <h1 className="text-2xl font-semibold text-navy-900">Hi {home.first_name}</h1>

      {pendingConsent?.next_action.consent_id && (
        <ConsentBanner consentId={pendingConsent.next_action.consent_id} />
      )}

      {home.applications.length === 0 ? (
        <EmptyState
          title="No application yet"
          body="Start your application to get your numbers."
          action={<Button onClick={() => router.push("/apply")}>Start your application</Button>}
        />
      ) : (
        <div className="flex flex-col gap-4">
          {home.applications.map((application) => (
            <ApplicationCard key={application.id} application={application} />
          ))}
        </div>
      )}
    </main>
  );
}
