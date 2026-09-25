import { Suspense } from "react";

import { ReportView } from "../../../features/report";

interface ReportPageRouteProps {
  // Next 15: dynamic route `params` is a Promise on a page component.
  params: Promise<{ token: string }>;
}

/**
 * `/report/{token}` (CQ-022 spec.md). `src/middleware.ts` already gates
 * this route behind a borrower session (redirecting a signed-out visitor
 * to `/login?next=/report/{token}`, H2); `ReportView` does the actual
 * fetch and renders the loading/not-found/loaded states. Wrapped in
 * `Suspense` because `ReportView` calls `useSearchParams()` (for `?option=`
 * — AC3), which Next.js requires a Suspense boundary for.
 */
export default async function ReportPageRoute({ params }: ReportPageRouteProps) {
  const { token } = await params;

  return (
    <Suspense
      fallback={
        <main role="status" className="p-8 text-sm text-neutral-600">
          Loading your report…
        </main>
      }
    >
      <ReportView token={token} />
    </Suspense>
  );
}
