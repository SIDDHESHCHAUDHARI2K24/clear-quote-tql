"use client";

import { MoneyInput, MultiSelect, Select } from "@cq/ui";

import { STATUS_OPTIONS, STRATEGY_OPTIONS, type ApplicationFilters } from "../filters";
import type { LoOption } from "../types";
import { US_STATE_OPTIONS } from "../us-states";

export interface ApplicationsFilterBarProps {
  filters: ApplicationFilters;
  onChange: (patch: Partial<ApplicationFilters>) => void;
  onClear: () => void;
  showLoFilter: boolean;
  loOptions: LoOption[];
}

const HAS_PROPERTY_OPTIONS: { value: ApplicationFilters["hasProperty"]; label: string }[] = [
  { value: "", label: "Any" },
  { value: "true", label: "Has property" },
  { value: "false", label: "TBD" },
];

const TOGGLE_BUTTON_BASE = "h-10 rounded-md border px-3 text-sm font-medium";
const TOGGLE_BUTTON_ACTIVE = "border-navy-500 bg-navy-50 text-navy-900";
const TOGGLE_BUTTON_INACTIVE = "border-neutral-200 text-neutral-600 hover:bg-neutral-50";
const TEXT_INPUT_CLASSES =
  "h-10 rounded-md border border-neutral-200 bg-neutral-0 px-3 text-navy-900 outline-none focus:border-navy-500";

/**
 * spec.md CQ-027 "Frontend": search, status multi-select, strategy chips,
 * amount range, state select, has-property toggle, date range and (for a
 * Manager/Admin) an LO select, plus "Clear filters". Every change goes
 * through `onChange`, which `useApplicationFilters` turns into a URL push
 * (AC6) -- this component holds no state of its own.
 */
export function ApplicationsFilterBar({
  filters,
  onChange,
  onClear,
  showLoFilter,
  loOptions,
}: ApplicationsFilterBarProps) {
  return (
    <div className="flex flex-col gap-4 rounded-md border border-neutral-200 bg-neutral-0 p-4">
      <div className="flex flex-wrap items-end gap-4">
        <div className="flex min-w-48 flex-col gap-1">
          <label htmlFor="applications-q" className="text-sm font-medium text-navy-900">
            Search
          </label>
          <input
            id="applications-q"
            type="search"
            value={filters.q}
            onChange={(e) => onChange({ q: e.target.value })}
            placeholder="Client name or email"
            className={TEXT_INPUT_CLASSES}
          />
        </div>

        <MultiSelect
          label="Status"
          options={STATUS_OPTIONS}
          value={filters.status}
          onChange={(status) => onChange({ status })}
        />

        <fieldset className="flex flex-col gap-1">
          <legend className="text-sm font-medium text-navy-900">Strategy</legend>
          <div className="flex gap-1">
            {STRATEGY_OPTIONS.map((option) => {
              const active = filters.strategy.includes(option.value);
              return (
                <button
                  key={option.value}
                  type="button"
                  aria-pressed={active}
                  onClick={() =>
                    onChange({
                      strategy: active
                        ? filters.strategy.filter((v) => v !== option.value)
                        : [...filters.strategy, option.value],
                    })
                  }
                  className={`${TOGGLE_BUTTON_BASE} ${active ? TOGGLE_BUTTON_ACTIVE : TOGGLE_BUTTON_INACTIVE}`}
                >
                  {option.label}
                </button>
              );
            })}
          </div>
        </fieldset>

        <div className="flex flex-col gap-1">
          <span className="text-sm font-medium text-navy-900">Purchase price</span>
          <div className="flex items-center gap-2">
            <MoneyInput
              aria-label="Minimum purchase price"
              value={filters.amountMin}
              onChange={(amountMin) => onChange({ amountMin })}
            />
            <span aria-hidden="true" className="text-neutral-400">
              –
            </span>
            <MoneyInput
              aria-label="Maximum purchase price"
              value={filters.amountMax}
              onChange={(amountMax) => onChange({ amountMax })}
            />
          </div>
        </div>

        <Select
          label="State"
          options={US_STATE_OPTIONS}
          value={filters.state}
          onChange={(state) => onChange({ state })}
          placeholder="Any"
        />

        <fieldset className="flex flex-col gap-1">
          <legend className="text-sm font-medium text-navy-900">Property</legend>
          <div className="flex gap-1" role="radiogroup" aria-label="Property">
            {HAS_PROPERTY_OPTIONS.map((option) => (
              <button
                key={option.value || "any"}
                type="button"
                role="radio"
                aria-checked={filters.hasProperty === option.value}
                onClick={() => onChange({ hasProperty: option.value })}
                className={`${TOGGLE_BUTTON_BASE} ${
                  filters.hasProperty === option.value
                    ? TOGGLE_BUTTON_ACTIVE
                    : TOGGLE_BUTTON_INACTIVE
                }`}
              >
                {option.label}
              </button>
            ))}
          </div>
        </fieldset>

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

        {showLoFilter && (
          <Select
            label="LO"
            options={loOptions.map((lo) => ({ value: lo.id, label: lo.full_name }))}
            value={filters.loId}
            onChange={(loId) => onChange({ loId })}
            placeholder="All LOs"
          />
        )}

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
