"use client";

import type { ReactNode } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";

import { UserMenu } from "./UserMenu";

export const STAFF_NAV_ITEMS = [
  { href: "/", label: "Dashboard" },
  { href: "/clients", label: "Clients" },
  { href: "/applications", label: "Applications" },
  { href: "/outbox", label: "Outbox" },
] as const;

function isActive(pathname: string, href: string): boolean {
  if (href === "/") return pathname === "/";
  return pathname === href || pathname.startsWith(`${href}/`);
}

/**
 * P5/P6 foundation (E5): the LO console chrome around every `(staff)`
 * page -- top nav (Dashboard, Clients, Applications, Outbox) and the user
 * menu. Rendered inside `StaffSessionProvider`.
 */
export function StaffShell({ children }: { children: ReactNode }) {
  const pathname = usePathname() ?? "/";

  return (
    <div className="flex min-h-screen flex-col bg-neutral-50">
      <header className="bg-navy-900 text-neutral-0">
        <div className="flex flex-wrap items-center justify-between gap-2 px-6 py-2">
          <div className="flex flex-wrap items-center gap-6">
            <Link href="/" className="text-md font-semibold text-neutral-0">
              Clear Quote
            </Link>
            <nav aria-label="Main">
              <ul className="flex flex-wrap items-center gap-1">
                {STAFF_NAV_ITEMS.map((item) => {
                  const active = isActive(pathname, item.href);
                  return (
                    <li key={item.href}>
                      <Link
                        href={item.href}
                        aria-current={active ? "page" : undefined}
                        className={
                          active
                            ? "rounded-md bg-navy-700 px-3 py-2 text-sm font-medium text-neutral-0"
                            : "rounded-md px-3 py-2 text-sm text-navy-100 hover:bg-navy-700 hover:text-neutral-0"
                        }
                      >
                        {item.label}
                      </Link>
                    </li>
                  );
                })}
              </ul>
            </nav>
          </div>
          <UserMenu />
        </div>
      </header>
      <div className="flex-1">{children}</div>
    </div>
  );
}
