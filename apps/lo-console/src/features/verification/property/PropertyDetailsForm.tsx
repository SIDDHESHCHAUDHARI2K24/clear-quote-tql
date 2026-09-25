"use client";

import { useState } from "react";

import { Select } from "@cq/ui";

import { patchProperty, runSectionAction } from "../shared";
import type { PropertyType, SectionField, SectionResponse } from "../shared";

export interface PropertyDetailsFormProps {
  applicationId: string;
  /** The "property" record's `property_type`/`number_of_units` fields (read
   * only there, per service.py -- edited only through `PATCH /property`). */
  propertyTypeField?: SectionField;
  unitsField?: SectionField;
  applyResult: (section: SectionResponse) => void;
}

const PROPERTY_TYPE_OPTIONS = [
  { value: "single_family", label: "Single family" },
  { value: "two_to_four_unit", label: "2-4 unit" },
  { value: "condo", label: "Condo" },
  { value: "townhome", label: "Townhome" },
];

export function PropertyDetailsForm({
  applicationId,
  propertyTypeField,
  unitsField,
  applyResult,
}: PropertyDetailsFormProps) {
  const [editing, setEditing] = useState(false);
  const [propertyType, setPropertyType] = useState(String(propertyTypeField?.value ?? ""));
  const [units, setUnits] = useState(String(unitsField?.value ?? ""));
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!editing) {
    return (
      <button
        type="button"
        onClick={() => {
          setPropertyType(String(propertyTypeField?.value ?? ""));
          setUnits(String(unitsField?.value ?? ""));
          setEditing(true);
        }}
        className="w-fit text-xs font-medium text-navy-600 underline"
      >
        Edit type / units
      </button>
    );
  }

  async function save() {
    setSaving(true);
    setError(null);
    // A non-numeric `units` value must fail loudly, not silently save as a
    // field-clear: `Number("abc")` is `NaN`, and `NaN` serializes to `null`
    // over the wire (code-review finding, same bug as `FieldRow`'s
    // `draftToValue`).
    let parsedUnits: number | null = null;
    if (units.trim() !== "") {
      parsedUnits = Number(units);
      if (Number.isNaN(parsedUnits)) {
        setSaving(false);
        setError("Units: enter a number.");
        return;
      }
    }
    const result = await runSectionAction(
      () =>
        patchProperty(applicationId, {
          property_type: (propertyType || null) as PropertyType | null,
          number_of_units: parsedUnits,
        }),
      "Could not save the property details.",
    );
    setSaving(false);
    if (!result.ok) {
      setError(result.message);
      return;
    }
    applyResult(result.section);
    setEditing(false);
  }

  return (
    <div className="flex flex-col gap-2 rounded-md border border-neutral-200 p-3">
      <div className="flex flex-wrap items-end gap-2">
        <Select
          label="Property type"
          options={PROPERTY_TYPE_OPTIONS}
          value={propertyType}
          onChange={setPropertyType}
        />
        <div className="flex flex-col gap-1">
          <label htmlFor="property-units" className="text-sm font-medium text-navy-900">
            Units
          </label>
          <input
            id="property-units"
            aria-label="Units"
            inputMode="numeric"
            value={units}
            onChange={(e) => setUnits(e.target.value)}
            className="h-10 w-20 rounded-md border border-neutral-200 px-2 text-sm"
          />
        </div>
      </div>
      <div className="flex items-center gap-2">
        <button
          type="button"
          onClick={() => void save()}
          disabled={saving}
          className="rounded-md bg-navy-700 px-3 py-1.5 text-xs font-medium text-neutral-0 disabled:opacity-50"
        >
          Save
        </button>
        <button
          type="button"
          onClick={() => setEditing(false)}
          disabled={saving}
          className="text-xs font-medium text-neutral-600 underline"
        >
          Cancel
        </button>
      </div>
      {error && <p className="text-xs text-status-danger">{error}</p>}
    </div>
  );
}
