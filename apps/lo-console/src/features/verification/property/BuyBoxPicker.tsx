"use client";

import { useEffect, useState } from "react";

import { MultiSelect } from "@cq/ui";

import { US_STATE_OPTIONS } from "../../applications/us-states";
import { fetchMetros, patchProperty, runSectionAction } from "../shared";
import type { PropertySummary, SectionResponse, StateMetros } from "../shared";

export interface BuyBoxPickerProps {
  applicationId: string;
  property: PropertySummary;
  applyResult: (section: SectionResponse) => void;
}

// spec.md Tab 5: "a two-tier buy-box picker: MultiSelect states -> metros"
// (AC6: picking FL then Tampa and Orlando stores both metros). States commit
// immediately (the backend prunes any now-invalid metros itself); metros are
// then chosen from `GET /reference/metros?states=...` for the *committed*
// states, refetched whenever `buy_box_states` changes.
export function BuyBoxPicker({ applicationId, property, applyResult }: BuyBoxPickerProps) {
  const [metroOptions, setMetroOptions] = useState<StateMetros[]>([]);
  const [metrosLoading, setMetrosLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const states = property.buy_box_states;

  useEffect(() => {
    let cancelled = false;
    if (states.length === 0) {
      setMetroOptions([]);
      return;
    }
    setMetrosLoading(true);
    fetchMetros(states)
      .then(({ data }) => {
        if (!cancelled && data) setMetroOptions(data.states);
      })
      .finally(() => {
        if (!cancelled) setMetrosLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [states.join(",")]); // eslint-disable-line react-hooks/exhaustive-deps -- refetch only when the actual state list changes

  async function saveStates(next: string[]) {
    setError(null);
    const result = await runSectionAction(
      () => patchProperty(applicationId, { buy_box_states: next }),
      "Could not update the buy-box states.",
    );
    if (!result.ok) setError(result.message);
    else applyResult(result.section);
  }

  async function saveMetros(next: string[]) {
    setError(null);
    const result = await runSectionAction(
      () => patchProperty(applicationId, { buy_box_metros: next }),
      "Could not update the buy-box metros.",
    );
    if (!result.ok) setError(result.message);
    else applyResult(result.section);
  }

  const metroSelectOptions = metroOptions
    .flatMap((entry) =>
      entry.metros.map((metro) => ({ value: metro, label: `${metro} (${entry.state})` })),
    )
    .filter((option, index, all) => all.findIndex((o) => o.value === option.value) === index);

  return (
    <div className="flex flex-col gap-2">
      <h4 className="text-sm font-semibold text-navy-900">Buy-box</h4>
      <div className="flex flex-wrap gap-4">
        <MultiSelect
          label="States"
          options={US_STATE_OPTIONS}
          value={states}
          onChange={(next) => void saveStates(next)}
        />
        <MultiSelect
          label="Metros"
          options={metroSelectOptions}
          value={property.buy_box_metros}
          onChange={(next) => void saveMetros(next)}
          disabled={states.length === 0 || metrosLoading}
          placeholder={states.length === 0 ? "Pick states first" : "Any"}
        />
      </div>
      {error && <p className="text-xs text-status-danger">{error}</p>}
    </div>
  );
}
