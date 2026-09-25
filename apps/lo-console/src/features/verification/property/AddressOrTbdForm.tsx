"use client";

import { useState } from "react";

import { Select } from "@cq/ui";

import { US_STATE_OPTIONS } from "../../applications/us-states";
import { patchProperty, runSectionAction } from "../shared";
import type { PropertySummary, SectionResponse } from "../shared";

export interface AddressOrTbdFormProps {
  applicationId: string;
  property: PropertySummary;
  applyResult: (section: SectionResponse) => void;
}

const EMPTY_ADDRESS = { street_address: "", city: "", state: "", zip: "", county: "" };

// spec.md Tab 5: "address or TBD" + "Enter address" / toggle. The TBD label
// lives here on the tab itself (plan.md decision #30) -- CQ-016's sticky
// header has no `address_status` field to read.
export function AddressOrTbdForm({ applicationId, property, applyResult }: AddressOrTbdFormProps) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(EMPTY_ADDRESS);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submitAddress() {
    setSaving(true);
    setError(null);
    const result = await runSectionAction(
      () =>
        patchProperty(applicationId, {
          address: {
            street_address: draft.street_address,
            city: draft.city,
            state: draft.state,
            zip: draft.zip,
            county: draft.county || null,
          },
        }),
      "Could not save the address.",
    );
    setSaving(false);
    if (!result.ok) {
      setError(result.message);
      return;
    }
    applyResult(result.section);
    setEditing(false);
    setDraft(EMPTY_ADDRESS);
  }

  async function markTbd() {
    setSaving(true);
    setError(null);
    const result = await runSectionAction(
      () => patchProperty(applicationId, { tbd: true }),
      "Could not mark the property TBD.",
    );
    setSaving(false);
    if (!result.ok) setError(result.message);
    else applyResult(result.section);
  }

  if (property.tbd && !editing) {
    return (
      <div className="flex flex-col gap-2">
        <span
          data-testid="property-tbd-label"
          className="inline-flex w-fit items-center rounded-full bg-status-warning/10 px-2 py-0.5 text-xs font-medium text-status-warning"
        >
          TBD
        </span>
        <p className="text-sm text-neutral-600">No specific address yet.</p>
        <button
          type="button"
          onClick={() => setEditing(true)}
          className="w-fit text-xs font-medium text-navy-600 underline"
        >
          Enter address
        </button>
        {error && <p className="text-xs text-status-danger">{error}</p>}
      </div>
    );
  }

  if (!editing) {
    return (
      <button
        type="button"
        onClick={() => void markTbd()}
        disabled={saving}
        className="w-fit text-xs font-medium text-navy-600 underline disabled:opacity-50"
      >
        Mark TBD
      </button>
    );
  }

  return (
    <div className="flex flex-col gap-2 rounded-md border border-neutral-200 p-3">
      <h4 className="text-sm font-semibold text-navy-900">Enter address</h4>
      <input
        aria-label="Street address"
        placeholder="Street address"
        value={draft.street_address}
        onChange={(e) => setDraft((d) => ({ ...d, street_address: e.target.value }))}
        className="h-9 rounded-md border border-neutral-200 px-2 text-sm"
      />
      <div className="flex flex-wrap gap-2">
        <input
          aria-label="City"
          placeholder="City"
          value={draft.city}
          onChange={(e) => setDraft((d) => ({ ...d, city: e.target.value }))}
          className="h-9 flex-1 rounded-md border border-neutral-200 px-2 text-sm"
        />
        <Select
          label="State"
          options={US_STATE_OPTIONS}
          value={draft.state}
          onChange={(value) => setDraft((d) => ({ ...d, state: value }))}
          placeholder="Select"
        />
        <input
          aria-label="Zip"
          placeholder="Zip"
          value={draft.zip}
          onChange={(e) => setDraft((d) => ({ ...d, zip: e.target.value }))}
          className="h-9 w-24 rounded-md border border-neutral-200 px-2 text-sm"
        />
      </div>
      <div className="flex items-center gap-2">
        <button
          type="button"
          onClick={() => void submitAddress()}
          disabled={saving}
          className="rounded-md bg-navy-700 px-3 py-1.5 text-xs font-medium text-neutral-0 disabled:opacity-50"
        >
          Save address
        </button>
        <button
          type="button"
          onClick={() => {
            setEditing(false);
            setError(null);
          }}
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
