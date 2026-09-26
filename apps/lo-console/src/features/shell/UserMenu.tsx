"use client";

import { useEffect, useId, useRef, useState } from "react";
import type { KeyboardEvent as ReactKeyboardEvent } from "react";
import Link from "next/link";

import { ROLE_LABELS } from "../auth";
import { useStaffSession } from "./StaffSessionProvider";

const ITEM_CLASSES =
  "block w-full rounded px-3 py-2 text-left text-sm text-navy-900 hover:bg-navy-50 focus:bg-navy-50 focus:outline-none";

/**
 * The signed-in user's name + role, the Admin-only "Integrations" and
 * "Settings" links (E5) and Sign out. A disclosure (button +
 * `aria-expanded`), closed by Escape (focus back to the button), an outside
 * click, or following a link.
 */
export function UserMenu() {
  const { user, role, isAdmin, logout } = useStaffSession();
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
        className="flex items-center gap-2 rounded-md px-3 py-2 text-sm text-neutral-0 hover:bg-navy-700"
      >
        <span className="font-medium">{user.full_name}</span>
        <span aria-hidden="true">▾</span>
      </button>
      {isOpen && (
        <div
          id={panelId}
          className="absolute top-full right-0 z-40 mt-1 w-56 rounded-md border border-neutral-200 bg-neutral-0 p-1 shadow-lg"
        >
          <p className="px-3 py-2 text-sm text-neutral-600" data-testid="user-menu-identity">
            Signed in as {user.full_name} ({ROLE_LABELS[role]})
          </p>
          <ul className="flex flex-col">
            {isAdmin && (
              <>
                <li>
                  <Link
                    href="/admin/integrations"
                    className={ITEM_CLASSES}
                    onClick={() => setIsOpen(false)}
                  >
                    Integrations
                  </Link>
                </li>
                <li>
                  <Link
                    href="/admin/settings"
                    className={ITEM_CLASSES}
                    onClick={() => setIsOpen(false)}
                  >
                    Settings
                  </Link>
                </li>
              </>
            )}
            <li>
              <button type="button" className={ITEM_CLASSES} onClick={() => void logout()}>
                Sign out
              </button>
            </li>
          </ul>
        </div>
      )}
    </div>
  );
}
