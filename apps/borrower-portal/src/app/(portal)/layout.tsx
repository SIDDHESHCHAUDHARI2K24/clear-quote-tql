import type { ReactNode } from "react";

import { ToastProvider } from "@cq/ui";

import { BorrowerSessionProvider, PortalShell } from "../../features/shell";

// P5/P6 foundation (E6): every signed-in portal page lives in this
// `(portal)` route group (URLs unchanged). `/login`, `/signup`,
// `/gallery/**` and `/report/[token]` (CQ-022, which has its own report
// chrome) stay outside it.
//
// `ToastProvider` wraps everything else (review round 1) so any page or
// feature under `(portal)` can call `useToast()`.
export default function PortalLayout({ children }: { children: ReactNode }) {
  return (
    <ToastProvider>
      <BorrowerSessionProvider>
        <PortalShell>{children}</PortalShell>
      </BorrowerSessionProvider>
    </ToastProvider>
  );
}
