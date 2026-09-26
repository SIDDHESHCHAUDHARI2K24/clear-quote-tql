import type { ReactNode } from "react";

import { AdminGuard } from "../../../features/shell";

// P5/P6 foundation (E5): every /admin/* page is Admin-only (client-side
// gate; the API enforces require_roles(admin) too).
export default function AdminLayout({ children }: { children: ReactNode }) {
  return <AdminGuard>{children}</AdminGuard>;
}
