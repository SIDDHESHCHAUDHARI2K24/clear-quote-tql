"use client";

import { useEffect, useId, useRef, useState } from "react";
import type { KeyboardEvent as ReactKeyboardEvent, ReactNode } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";

import { useBorrowerSession } from "./BorrowerSessionProvider";

export const PORTAL_NAV_ITEMS = [
  { href: "/", label: "Home" },
  { href: "/support", label: "Support" },
] as const;

// Placeholder licensing text until real TQL details exist (CQ-035/036).
export const NMLS_PLACEHOLDER = "NMLS #0000000 (placeholder)";

function AccountMenu() {
  const { me, logout } = useBorrowerSession();
  const [isOpen, setIsOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const buttonRef = useRef<HTMLButtonElement>(null);
  const panelId = useId();

  useEffect(() => {
    if (!isOpen) return;
    const onPointerDown = (e: MouseEvent) => {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) setIsOpen(false);
    };
    document.addEventListener("mousedown", onPointerDown);
    return () => document.removeEventListener("mousedown", onPointerDown);
  }, [isOpen]);

  function onKeyDown(e: ReactKeyboardEvent<HTMLDivElement>) {
    if (e.key === "Escape" && isOpen) {
      setIsOpen(false);
      buttonRef.current?.focus();
    }
  }

  return (
    <div ref={rootRef} className="relative" onKeyDown={onKeyDown}>
      <button
        ref={buttonRef}
        type="button"
        aria-expanded={isOpen}
        aria-controls={panelId}
        onClick={() => setIsOpen((open) => !open)}
        className="flex items-center gap-1 rounded-md px-2 py-2 text-sm text-navy-900 hover:bg-navy-50"
      >
        <span className="sr-only">Account menu for </span>
        {me.first_name}
        <span aria-hidden="true">▾</span>
      </button>
      {isOpen && (
        <div
          id={panelId}
          className="absolute top-full right-0 z-40 mt-1 w-56 max-w-[calc(100vw-2rem)] rounded-md border border-neutral-200 bg-neutral-0 p-1 shadow-lg"
        >
          <p className="truncate px-3 py-2 text-sm text-neutral-600">{me.email}</p>
          <button
            type="button"
            onClick={() => void logout()}
            className="block w-full rounded px-3 py-2 text-left text-sm text-navy-900 hover:bg-navy-50 focus:bg-navy-50 focus:outline-none"
          >
            Sign out
          </button>
        </div>
      )}
    </div>
  );
}

/**
 * P5/P6 foundation (E6): the borrower portal chrome around every
 * `(portal)` page -- header (TQL logo text, Home, Support, account menu
 * with Sign out) and a footer with the core disclosures. Mobile first: it
 * fits a 375 px viewport without horizontal scroll.
 */
export function PortalShell({ children }: { children: ReactNode }) {
  const pathname = usePathname() ?? "/";

  return (
    <div className="flex min-h-screen flex-col bg-neutral-50">
      <header className="border-b border-neutral-200 bg-neutral-0">
        <div className="mx-auto flex max-w-4xl items-center justify-between gap-2 px-4 py-2">
          <Link
            href="/"
            className="text-lg font-bold tracking-wide text-navy-900"
            aria-label="TQL — Total Quality Lending, home"
          >
            TQL
          </Link>
          <div className="flex min-w-0 items-center gap-1">
            <nav aria-label="Main">
              <ul className="flex items-center gap-1">
                {PORTAL_NAV_ITEMS.map((item) => {
                  const active =
                    item.href === "/" ? pathname === "/" : pathname.startsWith(item.href);
                  return (
                    <li key={item.href}>
                      <Link
                        href={item.href}
                        aria-current={active ? "page" : undefined}
                        className={
                          active
                            ? "rounded-md bg-navy-50 px-2 py-2 text-sm font-medium text-navy-900"
                            : "rounded-md px-2 py-2 text-sm text-navy-700 hover:bg-navy-50"
                        }
                      >
                        {item.label}
                      </Link>
                    </li>
                  );
                })}
              </ul>
            </nav>
            <AccountMenu />
          </div>
        </div>
      </header>

      <div className="mx-auto w-full max-w-4xl flex-1 px-4 py-6">{children}</div>

      <footer className="border-t border-neutral-200 bg-neutral-0">
        <div className="mx-auto flex max-w-4xl flex-col gap-1 px-4 py-4 text-xs text-neutral-600">
          <p>
            Total Quality Lending · {NMLS_PLACEHOLDER} ·{" "}
            <span data-testid="equal-housing">Equal Housing Lender</span>
          </p>
          <p>
            Not a commitment to lend. Rates, payments and terms are estimates and subject to change;
            all loans are subject to credit approval, underwriting and property review.
          </p>
        </div>
      </footer>
    </div>
  );
}
