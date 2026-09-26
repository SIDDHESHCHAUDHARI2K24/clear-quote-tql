"use client";

import type { ReactNode } from "react";

import Link from "next/link";

import { EmptyState } from "@cq/ui";

import { useStaffSession } from "./StaffSessionProvider";

/**
 * P5/P6 foundation (E5): client-side gate for `/admin/*`. Non-admins see a
 * not-authorized state instead of the page. (The API still enforces
 * `require_roles(admin)` with 403 -- this only avoids rendering a screen
 * whose every call would fail.)
 */
export function AdminGuard({ children }: { children: ReactNode }) {
  const { isAdmin } = useStaffSession();

  if (!isAdmin) {
    return (
      <main className="mx-auto max-w-2xl p-8">
        <EmptyState
          title="Not authorized"
          body="This page is available to Admin users only."
          action={
            <Link href="/" className="text-sm font-medium text-navy-500 underline">
              Back to the dashboard
            </Link>
          }
        />
      </main>
    );
  }

  return <>{children}</>;
}
