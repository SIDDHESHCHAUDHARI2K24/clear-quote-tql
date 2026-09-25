"use client";

import { Card } from "@cq/ui";

import { AddressOrTbdForm } from "./AddressOrTbdForm";
import { BuyBoxPicker } from "./BuyBoxPicker";
import { PropertyDetailsForm } from "./PropertyDetailsForm";
import {
  FieldRow,
  FlagList,
  patchProperty,
  putField,
  revertField,
  runSectionAction,
  useSection,
} from "../shared";
import type { FieldRowOption } from "../shared";

const OCCUPANCY_OPTIONS: FieldRowOption[] = [
  { value: "primary", label: "Primary" },
  { value: "investment", label: "Investment" },
];

const STRATEGY_OPTIONS: FieldRowOption[] = [
  { value: "ltr", label: "LTR" },
  { value: "str", label: "STR" },
];

// The "property" record's own fields (street_address/city/state/zip/county/
// property_type/number_of_units) are `editable: false` on the wire --
// service.py's `_property()` marks them read-only there because they're
// edited only through `PATCH /property` (AddressOrTbdForm/
// PropertyDetailsForm below), never the generic `PUT /fields/{key}`.
const READ_ONLY_PROPERTY_KEYS = new Set([
  "property.street_address",
  "property.city",
  "property.state",
  "property.zip",
  "property.county",
]);

export interface PropertyTabProps {
  applicationId: string;
}

// spec.md Tab 5 "Property": address or TBD, county/state/zip, type, units,
// the recommend-matches toggle and the two-tier buy-box picker. Occupancy
// and investment strategy also render here (plan.md decision #28): the
// section API's `_property()` is the only tab builder that returns a
// `kind="loan"` record for those two fields -- Borrowers never gets them.
export function PropertyTab({ applicationId }: PropertyTabProps) {
  const { state, refetch, applyResult } = useSection(applicationId, "property");

  if (state.kind === "loading") {
    return <p className="px-6 py-4 text-sm text-neutral-600">Loading…</p>;
  }
  if (state.kind === "error") {
    return (
      <div className="px-6 py-4">
        <p className="text-sm text-status-danger">Couldn&apos;t load this tab.</p>
        <button type="button" className="text-sm underline" onClick={() => void refetch()}>
          Retry
        </button>
      </div>
    );
  }

  const { section } = state;
  const flagsByKey = new Map(section.flags.map((flag) => [flag.field_key, flag]));
  const loanRecord = section.records.find((record) => record.kind === "loan");
  const propertyRecord = section.records.find((record) => record.kind === "property");
  const property = section.property;

  function editField(fieldKey: string) {
    return async (value: string | number | boolean | null) => {
      const result = await runSectionAction(() => putField(applicationId, fieldKey, value));
      if (!result.ok) throw new Error(result.message);
      applyResult(result.section);
    };
  }

  function revertFieldFn(fieldKey: string) {
    return async () => {
      const result = await runSectionAction(() => revertField(applicationId, fieldKey));
      if (!result.ok) throw new Error(result.message);
      applyResult(result.section);
    };
  }

  async function toggleRecommendMatches(checked: boolean) {
    const result = await runSectionAction(
      () => patchProperty(applicationId, { recommend_matches: checked }),
      "Could not update recommend matches.",
    );
    if (result.ok) applyResult(result.section);
  }

  return (
    <div className="flex flex-col gap-4 px-6 py-4">
      <FlagList flags={section.flags} />

      {loanRecord && (
        <Card title="Loan">
          {loanRecord.fields.map((field) => (
            <FieldRow
              key={field.field_key}
              field={field}
              flag={flagsByKey.get(field.field_key)}
              kind="select"
              options={field.field_key === "occupancy_type" ? OCCUPANCY_OPTIONS : STRATEGY_OPTIONS}
              disabled={
                field.field_key === "investment_strategy" && section.occupancy !== "investment"
              }
              onSave={editField(field.field_key)}
              onRevert={field.overridden ? revertFieldFn(field.field_key) : undefined}
            />
          ))}
        </Card>
      )}

      {propertyRecord && property && (
        <Card title="Property">
          <div className="flex flex-col gap-4">
            <AddressOrTbdForm
              applicationId={applicationId}
              property={property}
              applyResult={applyResult}
            />

            <div className="flex flex-col">
              {propertyRecord.fields
                .filter((field) => READ_ONLY_PROPERTY_KEYS.has(field.field_key))
                .map((field) => (
                  <FieldRow
                    key={field.field_key}
                    field={field}
                    flag={flagsByKey.get(field.field_key)}
                    kind="text"
                    onSave={async () => {}}
                  />
                ))}
            </div>

            <PropertyDetailsForm
              applicationId={applicationId}
              propertyTypeField={propertyRecord.fields.find(
                (f) => f.field_key === "property.property_type",
              )}
              unitsField={propertyRecord.fields.find(
                (f) => f.field_key === "property.number_of_units",
              )}
              applyResult={applyResult}
            />

            <label className="flex w-fit items-center gap-2 text-sm text-navy-900">
              <input
                type="checkbox"
                checked={property.recommend_matches}
                onChange={(e) => void toggleRecommendMatches(e.target.checked)}
              />
              Recommend matches
            </label>

            <BuyBoxPicker
              applicationId={applicationId}
              property={property}
              applyResult={applyResult}
            />
          </div>
        </Card>
      )}
    </div>
  );
}
