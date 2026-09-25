import type { ReactNode } from "react";

import { ToastProvider } from "@cq/ui";

import { StaffSessionProvider, StaffShell } from "../../features/shell";

// P5/P6 foundation (E5): every signed-in LO console page lives in this
// `(staff)` route group (URLs unchanged -- a route group adds no path
// segment). `/login` and `/gallery/**` stay outside it.
//
// `ToastProvider` wraps everything else (review round 1) so any page or
// feature under `(staff)` can call `useToast()` -- e.g. CQ-020's "Sent",
// CQ-029's re-verify started/failed toasts.
export default function StaffLayout({ children }: { children: ReactNode }) {
  return (
    <ToastProvider>
      <StaffSessionProvider>
        <StaffShell>{children}</StaffShell>
      </StaffSessionProvider>
    </ToastProvider>
  );
}
