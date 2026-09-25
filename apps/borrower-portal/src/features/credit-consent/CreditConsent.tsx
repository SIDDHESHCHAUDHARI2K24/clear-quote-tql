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
  const [notice, setNotice] = useState<string | null>(null);

  const signIn = useCallback(() => {
    // Clear the stale cookie first, or the middleware bounces /login
    // straight back here (same pattern as `HomeView`); `next` brings the
    // borrower back to this request after signing in.
    api
      .POST("/api/v1/auth/borrower/logout")
      .catch(() => {})
      .finally(() => {
        router.replace(loginUrlFor(`/tasks/credit-check/${consentId}`));
      });
  }, [consentId, router]);

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
          signIn();
          return;
        }
        setState({ kind: "error" });
      })
      .catch(() => {
        setState({ kind: "error" });
      });
  }, [consentId, signIn]);

  useEffect(() => {
    void load();
    // Reload only when the id changes; `router` identity is not stable.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [consentId]);

  const handleDecided = useCallback((consent: PortalConsent) => {
    setNotice(null);
    setState({ kind: "loaded", consent });
  }, []);

  // A 409 on accept/decline: re-read the request and show where it stands
  // (the outcome if it was decided or expired, else the updated form).
  const handleStale = useCallback(() => {
    setNotice("This request changed since you opened it. Review it and try again.");
    void load();
  }, [load]);

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
        <ConsentForm
          // New text (a 409 CONSENT_TEXT_CHANGED re-fetch) remounts the form,
          // so the checkbox and signature must be given again for it.
          key={state.consent.text.sha256}
          consent={state.consent}
          onDecided={handleDecided}
          onStale={handleStale}
          onUnauthorized={signIn}
          notice={notice}
        />
      ) : (
        <ConsentOutcome consent={state.consent} />
      )}
    </main>
  );
}
