"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

import { useWorkspace } from "./WorkspaceProvider";

// spec.md: "The default tab is the first flagged tab, else `pricing` when
// status >= Priced, else `borrowers`" -- the API computes `default_tab`
// (plan.md decision #7); this just redirects `/applications/[id]` (the
// bare route, with no tab segment) there once the summary loads. Renders
// nothing itself -- `WorkspaceShell` already shows the loading skeleton
// behind it.
export function DefaultTabRedirect() {
  const router = useRouter();
  const { applicationId, state } = useWorkspace();

  useEffect(() => {
    if (state.kind === "ready") {
      router.replace(`/applications/${applicationId}/${state.summary.default_tab}`);
    }
  }, [state, applicationId, router]);

  return null;
}
