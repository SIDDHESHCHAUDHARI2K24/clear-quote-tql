import type { ReactNode } from "react";

import { StaffSessionProvider, StaffShell } from "../../features/shell";

// P5/P6 foundation (E5): every signed-in LO console page lives in this
// `(staff)` route group (URLs unchanged -- a route group adds no path
// segment). `/login` and `/gallery/**` stay outside it.
export default function StaffLayout({ children }: { children: ReactNode }) {
  return (
    <StaffSessionProvider>
      <StaffShell>{children}</StaffShell>
    </StaffSessionProvider>
  );
}
