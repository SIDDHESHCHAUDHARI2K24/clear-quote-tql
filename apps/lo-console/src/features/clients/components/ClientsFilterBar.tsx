"use client";

import { Select } from "@cq/ui";

import type { LoOption } from "../../applications";
import { HAS_ACTIVE_OPTIONS, type ClientFilters } from "../filters";

export interface ClientsFilterBarProps {
  filters: ClientFilters;
  onChange: (patch: Partial<ClientFilters>) => void;
  onClear: () => void;
  showLoFilter: boolean;
  loOptions: LoOption[];
}

const TEXT_INPUT_CLASSES =
  "h-10 rounded-md border border-neutral-200 bg-neutral-0 px-3 text-navy-900 outline-none focus:border-navy-500";
const TOGGLE_BUTTON_BASE = "h-10 rounded-md border px-3 text-sm font-medium";
const TOGGLE_BUTTON_ACTIVE = "border-navy-500 bg-navy-50 text-navy-900";
const TOGGLE_BUTTON_INACTIVE = "border-neutral-200 text-neutral-600 hover:bg-neutral-50";

/**
 * spec.md CQ-026 "Frontend": search (debounced by the caller), assigned LO
 * (Manager/Admin only), created date range, active-only toggle, plus
 * "Clear filters" -- mirrors `applications/components/ApplicationsFilterBar.tsx`.
 */
export function ClientsFilterBar({
  filters,
  onChange,
  onClear,
  showLoFilter,
  loOptions,
}: ClientsFilterBarProps) {
  return (
    <div className="flex flex-col gap-4 rounded-md border border-neutral-200 bg-neutral-0 p-4">
      <div className="flex flex-wrap items-end gap-4">
        <div className="flex min-w-48 flex-col gap-1">
          <label htmlFor="clients-q" className="text-sm font-medium text-navy-900">
            Search
          </label>
          <input
            id="clients-q"
            type="search"
            value={filters.q}
            onChange={(e) => onChange({ q: e.target.value })}
            placeholder="Name or email"
            className={TEXT_INPUT_CLASSES}
          />
        </div>

        {showLoFilter && (
          <Select
            label="LO"
            options={loOptions.map((lo) => ({ value: lo.id, label: lo.full_name }))}
            value={filters.loId}
            onChange={(loId) => onChange({ loId })}
            placeholder="All LOs"
          />
        )}

        <div className="flex flex-col gap-1">
          <span className="text-sm font-medium text-navy-900">Created</span>
          <div className="flex items-center gap-2">
            <input
              type="date"
              aria-label="Created from"
              value={filters.createdFrom}
              onChange={(e) => onChange({ createdFrom: e.target.value })}
              className={TEXT_INPUT_CLASSES}
            />
            <span aria-hidden="true" className="text-neutral-400">
              –
            </span>
            <input
              type="date"
              aria-label="Created to"
              value={filters.createdTo}
              onChange={(e) => onChange({ createdTo: e.target.value })}
              className={TEXT_INPUT_CLASSES}
            />
          </div>
        </div>

        <fieldset className="flex flex-col gap-1">
          <legend className="text-sm font-medium text-navy-900">Active</legend>
          <div className="flex gap-1" role="radiogroup" aria-label="Active">
            {HAS_ACTIVE_OPTIONS.map((option) => (
              <button
                key={option.value || "any"}
                type="button"
                role="radio"
                aria-checked={filters.hasActive === option.value}
                onClick={() => onChange({ hasActive: option.value })}
                className={`${TOGGLE_BUTTON_BASE} ${
                  filters.hasActive === option.value ? TOGGLE_BUTTON_ACTIVE : TOGGLE_BUTTON_INACTIVE
                }`}
              >
                {option.label}
              </button>
            ))}
          </div>
        </fieldset>

        <button
          type="button"
          onClick={onClear}
          className="h-10 rounded-md border border-neutral-200 px-3 text-sm font-medium text-navy-900 hover:bg-navy-50"
        >
          Clear filters
        </button>
      </div>
    </div>
  );
}
