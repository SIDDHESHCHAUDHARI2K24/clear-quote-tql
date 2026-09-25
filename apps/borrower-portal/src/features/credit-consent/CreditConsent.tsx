"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { api } from "../../lib/api-client";
import { loginUrlFor } from "../shell";

import { ConsentForm } from "./ConsentForm";
import { ConsentLoadError, ConsentNotFound, ConsentOutcome } from "./ConsentStates";
import type { PortalConsent } from "./api";
import { fetchConsent } from "./api";

type ViewState =
  | { kind: "loading" }
  | { kind: "not-found" }
  | { kind: "error" }
  | { kind: "loaded"; consent: PortalConsent };

/**
 * `/tasks/credit-check/[id]` (CQ-033): loads the request client-side so the
 * httpOnly borrower cookie rides along (same convention as `HomeView`).
 * Pending → the consent form; accepted / declined / expired → the matching
 * confirmation; 404 (unknown, or another borrower's request) → not found.
 */
export function CreditConsent({ consentId }: { consentId: string }) {
  const router = useRouter();
  const [state, setState] = useState<ViewState>({ kind: "loading" });

  const load = useCallback(() => {
    setState({ kind: "loading" });
    return fetchConsent(consentId)
      .then(({ data, response }) => {
        if (data) {
          setState({ kind: "loaded", consent: data });
          return;
        }
        if (response.status === 404 || response.status === 422) {
          setState({ kind: "not-found" });
          return;
        }
        if (response.status === 401) {
          // Clear the stale cookie first, or the middleware bounces /login
          // straight back here (same pattern as `HomeView`); `next` brings the
          // borrower back to this request after signing in.
          api
            .POST("/api/v1/auth/borrower/logout")
            .catch(() => {})
            .finally(() => {
              router.replace(loginUrlFor(`/tasks/credit-check/${consentId}`));
            });
          return;
        }
        setState({ kind: "error" });
      })
      .catch(() => {
        setState({ kind: "error" });
      });
  }, [consentId, router]);

  useEffect(() => {
    void load();
    // Reload only when the id changes; `router` identity is not stable.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [consentId]);

  const handleDecided = useCallback((consent: PortalConsent) => {
    setState({ kind: "loaded", consent });
  }, []);

  if (state.kind === "loading") {
    return (
      <main role="status" aria-live="polite" className="flex flex-col gap-4">
        <p className="text-sm text-neutral-600">Loading the request…</p>
        <div className="h-24 animate-pulse rounded-lg bg-neutral-100" aria-hidden="true" />
      </main>
    );
  }
  if (state.kind === "not-found") {
    return (
      <main className="mx-auto w-full max-w-2xl">
        <ConsentNotFound />
      </main>
    );
  }
  if (state.kind === "error") {
    return (
      <main className="mx-auto w-full max-w-2xl">
        <ConsentLoadError onRetry={() => void load()} />
      </main>
    );
  }
  return (
    <main className="mx-auto w-full max-w-2xl">
      {state.consent.status === "pending" ? (
        <ConsentForm consent={state.consent} onDecided={handleDecided} />
      ) : (
        <ConsentOutcome consent={state.consent} />
      )}
    </main>
  );
}
