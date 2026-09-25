import type { components } from "@cq/api-client";

// Display labels for `UserRole` (backend/app/core/enums.py). Kept here
// rather than inline so the home page and any later staff-facing screen
// (P3/P5) share one mapping.
export const ROLE_LABELS: Record<components["schemas"]["UserRole"], string> = {
  lo: "Loan Officer",
  manager: "Manager",
  admin: "Admin",
};
