"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";

import { ReportPage } from "@cq/ui";
import type { components } from "@cq/api-client";

import { parseBorrowerAction } from "../actions/api";
import { api } from "../../lib/api-client";

import { ReportActionsSlot } from "./ReportActionsSlot";
import { ReportMatchesSlot } from "./ReportMatchesSlot";

type PortalReport = components["schemas"]["PortalReportResponse"];

type ViewState =
  | { kind: "loading" }
  | { kind: "not-found" }
  | { kind: "error" }
  | { kind: "loaded"; report: PortalReport };

export interface ReportViewProps {
  token: string;
}

/**
 * `GET /api/v1/portal/reports/{token}` (CQ-022 spec.md), fetched
 * client-side (same convention as `src/app/page.tsx`'s `/me` check) so the
 * httpOnly `cq_borrower_session` cookie rides along via `credentials:
 * "include"` (`lib/api-client.ts`). `src/middleware.ts` already redirects a
 * fully signed-out visitor to `/login?next=/report/{token}` before this
 * component ever mounts; the 401 branch below only ever fires for a
 * present-but-no-longer-valid cookie (expired/revoked session), same as
 * the home page's own fallback. A 404 (foreign token, random token, or
 * `ensure_borrower_owns_client`'s 404 -- spec.md AC5) shows a friendly
 * not-found message, never the raw error.
 */
export function ReportView({ token }: ReportViewProps) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [state, setState] = useState<ViewState>({ kind: "loading" });

  // CQ-024: extracted from the effect below into its own callback so
  // `ReportActionsSlot` can re-run it after a borrower action (success or
  // 409) through the existing `renderActions` render-prop closure, without
  // adding a new prop to `ReportView`'s or `ReportPage`'s own interface
  // (plan.md Decision 8). `showLoadingState` is false for that re-fetch --
  // a successful action already knows the new state is coming and
  // shouldn't flash the whole page back to a loading skeleton.
  const loadReport = useCallback(
    (opts: { showLoadingState: boolean } = { showLoadingState: true }) => {
      if (opts.showLoadingState) setState({ kind: "loading" });

      return api
        .GET("/api/v1/portal/reports/{token}", { params: { path: { token } } })
        .then(({ data, response }) => {
          if (data) {
            setState({ kind: "loaded", report: data });
            return;
          }
          if (response.status === 401) {
            api
              .POST("/api/v1/auth/borrower/logout")
              .catch(() => {})
              .finally(() => {
                router.replace(`/login?next=${encodeURIComponent(`/report/${token}`)}`);
              });
            return;
          }
          // Only a real 404 (foreign token, random token, or
          // ensure_borrower_owns_client's 404 -- spec.md AC5) is a "not
          // found" report. Fresh-subagent review finding (fixed): a
          // transient 5xx/502 was previously shown as "not found" too,
          // hiding real backend errors behind a wrong "check your email"
          // message instead of "something went wrong, try reloading".
          if (response.status === 404) {
            setState({ kind: "not-found" });
            return;
          }
          setState({ kind: "error" });
        })
        .catch(() => {
          setState({ kind: "error" });
        });
    },
    [token, router],
  );

  useEffect(() => {
    // React discards a `setState` from an unmounted component's own
    // closures, so no extra "cancelled" bookkeeping is needed here beyond
    // what `loadReport` already does.
    void loadReport();
    // Re-fetch only when `token` itself changes. `searchParams` is read
    // fresh below at render time for the initial `?option=`, not something
    // that should retrigger a fetch when the user switches options.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  if (state.kind === "loading") {
    return (
      <main role="status" aria-live="polite" className="flex flex-col gap-4 p-8">
        <p className="text-sm text-neutral-600">Loading your report…</p>
        <div className="h-40 animate-pulse rounded-lg bg-neutral-100" aria-hidden="true" />
        <div className="h-24 animate-pulse rounded-lg bg-neutral-100" aria-hidden="true" />
        <div className="h-24 animate-pulse rounded-lg bg-neutral-100" aria-hidden="true" />
      </main>
    );
  }

  if (state.kind === "not-found") {
    return (
      <main className="mx-auto flex max-w-md flex-col items-center gap-3 p-8 text-center">
        <h1 className="text-xl font-semibold text-navy-900">We couldn&rsquo;t find that report</h1>
        <p className="text-neutral-600">
          This link may be out of date, or it belongs to a different account. Check your email for
          the latest link, or contact your loan officer.
        </p>
      </main>
    );
  }

  if (state.kind === "error") {
    return (
      <main className="mx-auto flex max-w-md flex-col items-center gap-3 p-8 text-center">
        <h1 className="text-xl font-semibold text-navy-900">Something went wrong</h1>
        <p className="text-neutral-600">Try reloading the page.</p>
      </main>
    );
  }

  const { report } = state;
  const optionParam = searchParams.get("option") ?? undefined;

  function handleSelectionChange(quoteId: string) {
    const params = new URLSearchParams(searchParams.toString());
    params.set("option", quoteId);
    router.replace(`/report/${token}?${params.toString()}`, { scroll: false });
  }

  return (
    // `<main>` (Lighthouse's `landmark-one-main` audit): the report is this
    // page's entire content, so it's the page's one main landmark.
    <main className="mx-auto flex max-w-[1120px] flex-col gap-6 p-4 sm:p-8">
      <ReportPage
        viewModel={report}
        initialSelectedId={optionParam}
        onSelectionChange={handleSelectionChange}
        newestReportHref={
          report.newest_report_token ? `/report/${report.newest_report_token}` : undefined
        }
        renderMatches={(vm) => <ReportMatchesSlot viewModel={vm} />}
        renderActions={(vm, selected) => (
          <ReportActionsSlot
            viewModel={vm}
            selectedOption={selected}
            token={token}
            borrowerAction={parseBorrowerAction(report.borrower_action)}
            onActionTaken={() => void loadReport({ showLoadingState: false })}
          />
        )}
      />
    </main>
  );
}
