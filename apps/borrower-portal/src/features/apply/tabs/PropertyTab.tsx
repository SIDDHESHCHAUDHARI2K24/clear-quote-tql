"use client";

import { MultiSelect, Select } from "@cq/ui";

import type { MetrosOut } from "../api";
import { Field } from "../fields";
import { getBool, getString, getStringArray } from "../paths";
import type { TabFormProps } from "./TabForm";

const OCCUPANCY_OPTIONS = [
  { value: "primary", label: "I'll live there" },
  { value: "ltr", label: "Long-term rental" },
  { value: "str", label: "Short-term rental" },
];

const HAS_PROPERTY_OPTIONS = [
  { value: "yes", label: "Yes, I have an address" },
  { value: "no", label: "Not yet" },
];

const DOWN_PAYMENT_OPTIONS: Record<string, { value: string; label: string }[]> = {
  primary: [
    { value: "0.03", label: "3%" },
    { value: "0.05", label: "5%" },
    { value: "0.10", label: "10%" },
    { value: "0.15", label: "15%" },
    { value: "0.20", label: "20%" },
  ],
  ltr: [
    { value: "0.15", label: "15%" },
    { value: "0.20", label: "20%" },
    { value: "0.25", label: "25%" },
  ],
  str: [
    { value: "0.15", label: "15%" },
    { value: "0.20", label: "20%" },
    { value: "0.25", label: "25%" },
  ],
};

export interface PropertyTabProps extends TabFormProps {
  metros: MetrosOut;
}

/** Tab 2 (spec.md table): occupancy, an address or a buy-box (states then
 * that state's metros -- the two-tier picker), target price, and a down
 * payment option gated by occupancy. */
export function PropertyTab({ data, set, errorFor, disabled, metros }: PropertyTabProps) {
  const occupancy = getString(data, "occupancy") || "primary";
  const hasProperty = getBool(data, "has_property");
  const selectedStates = getStringArray(data, "buy_box_states");
  const selectedMetros = getStringArray(data, "buy_box_metros");

  const selectedStateSet = new Set(selectedStates);
  const stateOptions = metros.states.map((s) => ({ value: s.state, label: s.state }));
  const metroOptions = metros.states
    .filter((s) => selectedStateSet.has(s.state))
    .flatMap((s) => s.metros.map((metro) => ({ value: metro, label: `${metro}, ${s.state}` })));

  function onStatesChange(next: string[]) {
    set("buy_box_states", next, "buy_box_states");
    // Drop any selected metro whose state was just deselected.
    const nextStateSet = new Set(next);
    const stillAllowed = new Set(
      metros.states.filter((s) => nextStateSet.has(s.state)).flatMap((s) => s.metros),
    );
    const keptMetros = selectedMetros.filter((m) => stillAllowed.has(m));
    if (keptMetros.length !== selectedMetros.length) {
      set("buy_box_metros", keptMetros, "buy_box_metros");
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <Select
        id="occupancy"
        label="What's this loan for?"
        options={OCCUPANCY_OPTIONS}
        value={occupancy}
        disabled={disabled}
        onChange={(value) => set("occupancy", value, "occupancy")}
        error={errorFor("occupancy")}
      />

      <Select
        id="has-property"
        label="Do you have a property in mind?"
        options={HAS_PROPERTY_OPTIONS}
        value={hasProperty ? "yes" : "no"}
        disabled={disabled}
        onChange={(value) => set("has_property", value === "yes", "has_property")}
      />

      {hasProperty ? (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <Field
            id="property-street"
            label="Street address"
            className="sm:col-span-2"
            value={getString(data, "address.street")}
            disabled={disabled}
            onChange={(e) => set("address.street", e.target.value, "address.street")}
            error={errorFor("address.street")}
          />
          <Field
            id="property-city"
            label="City"
            value={getString(data, "address.city")}
            disabled={disabled}
            onChange={(e) => set("address.city", e.target.value, "address.city")}
            error={errorFor("address.city")}
          />
          <div className="grid grid-cols-2 gap-3">
            <Field
              id="property-state"
              label="State"
              maxLength={2}
              value={getString(data, "address.state")}
              disabled={disabled}
              onChange={(e) => set("address.state", e.target.value, "address.state")}
              error={errorFor("address.state")}
            />
            <Field
              id="property-zip"
              label="ZIP"
              inputMode="numeric"
              maxLength={5}
              value={getString(data, "address.zip")}
              disabled={disabled}
              onChange={(e) => set("address.zip", e.target.value, "address.zip")}
              error={errorFor("address.zip")}
            />
          </div>
        </div>
      ) : (
        <div className="flex flex-col gap-3">
          <MultiSelect
            label="States"
            options={stateOptions}
            value={selectedStates}
            disabled={disabled}
            onChange={onStatesChange}
          />
          <MultiSelect
            label="Metros"
            options={metroOptions}
            value={selectedMetros}
            disabled={disabled || selectedStates.length === 0}
            placeholder={selectedStates.length === 0 ? "Choose a state first" : "Any"}
            onChange={(next) => set("buy_box_metros", next, "buy_box_metros")}
          />
          {errorFor("buy_box_metros") && (
            <p role="alert" className="text-xs text-status-danger">
              {errorFor("buy_box_metros")}
            </p>
          )}
        </div>
      )}

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <Field
          id="target-price"
          label="Target price"
          inputMode="decimal"
          value={getString(data, "target_price")}
          disabled={disabled}
          onChange={(e) => set("target_price", e.target.value, "target_price")}
          error={errorFor("target_price")}
        />
        <Select
          id="down-payment-pct"
          label="Down payment"
          options={DOWN_PAYMENT_OPTIONS[occupancy] ?? DOWN_PAYMENT_OPTIONS.primary}
          placeholder="Choose one"
          value={getString(data, "down_payment_pct")}
          disabled={disabled}
          onChange={(value) => set("down_payment_pct", value, "down_payment_pct")}
          error={errorFor("down_payment_pct")}
        />
      </div>
    </div>
  );
}
