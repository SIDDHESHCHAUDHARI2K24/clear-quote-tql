import type { ReactNode } from "react";

import { BorrowerSessionProvider, PortalShell } from "../../features/shell";

// P5/P6 foundation (E6): every signed-in portal page lives in this
// `(portal)` route group (URLs unchanged). `/login`, `/signup`,
// `/gallery/**` and `/report/[token]` (CQ-022, which has its own report
// chrome) stay outside it.
export default function PortalLayout({ children }: { children: ReactNode }) {
  return (
    <BorrowerSessionProvider>
      <PortalShell>{children}</PortalShell>
    </BorrowerSessionProvider>
  );
}
