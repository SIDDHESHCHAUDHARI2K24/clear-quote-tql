import { Suspense } from "react";

import { DashboardPage } from "../../features/dashboard";

// `/` -- the LO console landing page (CQ-025 spec.md). Wrapped in
// `Suspense` because `DashboardPage` calls `useSearchParams()` (for
// `?lo_id=`), which Next.js requires a Suspense boundary for (same
// precedent as the borrower portal's `/report/[token]` route).
export default function Page() {
  return (
    <Suspense
      fallback={
        <div role="status" aria-label="Loading dashboard" className="p-6 text-sm text-neutral-600">
          Loading dashboard…
        </div>
      }
    >
      <DashboardPage />
    </Suspense>
  );
}
