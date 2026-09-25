"use client";

import { TAB_LABELS, TAB_ORDER } from "./api";
import type { Tab } from "./api";

export interface StepperProps {
  activeTab: Tab;
  /** The server's `current_tab` (plan.md decision 4): the first tab that
   * does not yet validate. Every tab up to and including this one is
   * reachable; the spec's "the next tab unlocks only when the current tab
   * validates; any completed tab can be revisited." */
  unlockedTab: Tab;
  onSelect: (tab: Tab) => void;
}

export function Stepper({ activeTab, unlockedTab, onSelect }: StepperProps) {
  const unlockedIndex = TAB_ORDER.indexOf(unlockedTab);

  return (
    <nav aria-label="Application steps">
      <ol className="flex flex-wrap gap-2">
        {TAB_ORDER.map((tab, index) => {
          const isActive = tab === activeTab;
          const isUnlocked = index <= unlockedIndex;
          return (
            <li key={tab}>
              <button
                type="button"
                disabled={!isUnlocked}
                aria-current={isActive ? "step" : undefined}
                onClick={() => onSelect(tab)}
                className={
                  isActive
                    ? "flex items-center gap-2 rounded-full border border-navy-500 bg-navy-500 px-3 py-1.5 text-sm font-medium text-neutral-0"
                    : isUnlocked
                      ? "flex items-center gap-2 rounded-full border border-neutral-200 bg-neutral-0 px-3 py-1.5 text-sm font-medium text-navy-900 hover:bg-navy-50"
                      : "flex items-center gap-2 rounded-full border border-neutral-100 bg-neutral-50 px-3 py-1.5 text-sm font-medium text-neutral-400 disabled:cursor-not-allowed"
                }
              >
                <span aria-hidden="true">{index + 1}</span>
                {TAB_LABELS[tab]}
              </button>
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
