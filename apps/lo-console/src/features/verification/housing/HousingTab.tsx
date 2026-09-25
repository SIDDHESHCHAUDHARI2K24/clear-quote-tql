"use client";

import { useState } from "react";

import { Button, Card } from "@cq/ui";

import {
  FieldRow,
  FlagList,
  addHousing,
  fieldBySuffix,
  putField,
  revertField,
  runSectionAction,
  useSection,
} from "../shared";
import type {
  HousingCreate,
  SectionFlag,
  SectionRecord,
  SectionResponse,
  UseSectionResult,
} from "../shared";

type HousingSummary = NonNullable<SectionResponse["housing"]>;

const HOUSING_STATUS_OPTIONS = [
  { value: "own", label: "Own" },
  { value: "rent", label: "Rent" },
  { value: "rent_free", label: "Rent-free" },
];

// Order + kind for the housing_history row's fixed fields (plan.md's tab
// spec passed down by the coordinator -- suffix matches the backend's
// `housing_history.{row_id}.{suffix}` field_key exactly).
const FIELD_SPECS: Array<{
  suffix: string;
  kind: "text" | "number" | "select" | "boolean";
}> = [
  { suffix: "street_address", kind: "text" },
  { suffix: "city", kind: "text" },
  { suffix: "state", kind: "text" },
  { suffix: "zip", kind: "text" },
  { suffix: "housing_status", kind: "select" },
  { suffix: "residence_years", kind: "number" },
  { suffix: "residence_months", kind: "number" },
  { suffix: "vom_completed", kind: "boolean" },
];

export function HousingTab({ applicationId }: { applicationId: string }) {
  const { state, refetch, applyResult } = useSection(applicationId, "housing");
  const [addOpen, setAddOpen] = useState(false);

  if (state.kind === "loading")
    return <p className="px-6 py-4 text-sm text-neutral-600">Loading…</p>;
  if (state.kind === "error")
    return (
      <div className="px-6 py-4">
        <p className="text-sm text-status-danger">Couldn&apos;t load this tab.</p>
        <button type="button" className="text-sm underline" onClick={() => refetch()}>
          Retry
        </button>
      </div>
    );

  const { section } = state;
  const flagsByKey = new Map(section.flags.map((flag) => [flag.field_key, flag]));

  return (
    <div className="flex flex-col gap-4 px-6 py-4">
      <FlagList flags={section.flags} />
      {section.housing && <HousingSummaryBanner housing={section.housing} />}

      {section.records.map((record, index) => (
        <HousingRecordCard
          // `service.py`'s `_row_record` always sets a real row id for
          // `housing_history` records (only the credit tab's synthetic
          // "credit" record and the property tab's "loan" record can have
          // `id: null`, neither of which appears here), so this is a stable
          // key, not an index (react-doctor/no-array-index-as-key).
          key={record.id as string}
          applicationId={applicationId}
          record={record}
          index={index}
          flagsByKey={flagsByKey}
          applyResult={applyResult}
        />
      ))}

      <AddPriorAddressForm
        applicationId={applicationId}
        open={addOpen}
        onOpenChange={setAddOpen}
        applyResult={applyResult}
      />
    </div>
  );
}

/** AC2's "total months vs 24" summary (spec.md CQ-028): the backend has
 * already summed `residence_years*12 + residence_months` across every row
 * into `section.housing.total_months`, so this only formats and colors it. */
function HousingSummaryBanner({ housing }: { housing: HousingSummary }) {
  const { total_months, required_months, meets_requirement } = housing;
  return (
    <div
      role="status"
      className={`rounded-md border-l-4 px-3 py-2 text-sm font-semibold ${
        meets_requirement
          ? "border-status-success bg-status-success/5 text-status-success"
          : "border-status-warning bg-status-warning/5 text-status-warning"
      }`}
    >
      Housing history: {total_months} / {required_months} months
      {meets_requirement ? " — requirement met" : " — below the 24-month requirement"}
    </div>
  );
}

function HousingRecordCard({
  applicationId,
  record,
  index,
  flagsByKey,
  applyResult,
}: {
  applicationId: string;
  record: SectionRecord;
  index: number;
  flagsByKey: Map<string, SectionFlag>;
  applyResult: UseSectionResult["applyResult"];
}) {
  const streetField = fieldBySuffix(record, "street_address");
  const title =
    index === 0
      ? "Current address"
      : (typeof streetField?.value === "string" && streetField.value) || `Prior address ${index}`;

  return (
    <Card title={title}>
      <div className="flex flex-col">
        {FIELD_SPECS.map(({ suffix, kind }) => {
          const field = fieldBySuffix(record, suffix);
          if (!field) return null;
          return (
            <FieldRow
              key={field.field_key}
              field={field}
              flag={flagsByKey.get(field.field_key)}
              kind={kind}
              options={suffix === "housing_status" ? HOUSING_STATUS_OPTIONS : undefined}
              onSave={async (value) => {
                const result = await runSectionAction(() =>
                  putField(applicationId, field.field_key, value),
                );
                if (!result.ok) throw new Error(result.message);
                applyResult(result.section);
              }}
              onRevert={
                field.overridden
                  ? async () => {
                      const result = await runSectionAction(() =>
                        revertField(applicationId, field.field_key),
                      );
                      if (!result.ok) throw new Error(result.message);
                      applyResult(result.section);
                    }
                  : undefined
              }
            />
          );
        })}
      </div>
    </Card>
  );
}

const EMPTY_DRAFT: HousingCreate = {
  street_address: "",
  city: "",
  state: "",
  zip: "",
  housing_status: "rent",
  residence_years: 0,
  residence_months: 0,
  vom_completed: false,
};

/** AC2's "add prior address" -- an inline `HousingCreate` form that closes
 * on a successful `POST /housing_history`. */
function AddPriorAddressForm({
  applicationId,
  open,
  onOpenChange,
  applyResult,
}: {
  applicationId: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  applyResult: UseSectionResult["applyResult"];
}) {
  const [draft, setDraft] = useState<HousingCreate>(EMPTY_DRAFT);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!open) {
    return (
      <Button
        variant="secondary"
        onClick={() => {
          setDraft(EMPTY_DRAFT);
          setError(null);
          onOpenChange(true);
        }}
      >
        Add prior address
      </Button>
    );
  }

  const submit = async () => {
    setSubmitting(true);
    setError(null);
    const result = await runSectionAction(() => addHousing(applicationId, draft));
    setSubmitting(false);
    if (!result.ok) {
      setError(result.message);
      return;
    }
    applyResult(result.section);
    setDraft(EMPTY_DRAFT);
    onOpenChange(false);
  };

  return (
    <Card title="Add prior address">
      <div className="flex flex-col gap-3">
        <label className="flex flex-col gap-1 text-sm">
          Street address
          <input
            aria-label="Street address"
            className="h-9 rounded-md border border-neutral-200 px-2 text-sm"
            value={draft.street_address}
            onChange={(e) => setDraft((d) => ({ ...d, street_address: e.target.value }))}
          />
        </label>
        <label className="flex flex-col gap-1 text-sm">
          City
          <input
            aria-label="City"
            className="h-9 rounded-md border border-neutral-200 px-2 text-sm"
            value={draft.city}
            onChange={(e) => setDraft((d) => ({ ...d, city: e.target.value }))}
          />
        </label>
        <div className="flex gap-3">
          <label className="flex flex-col gap-1 text-sm">
            State
            <input
              aria-label="State"
              maxLength={2}
              className="h-9 w-16 rounded-md border border-neutral-200 px-2 text-sm"
              value={draft.state}
              onChange={(e) => setDraft((d) => ({ ...d, state: e.target.value }))}
            />
          </label>
          <label className="flex flex-col gap-1 text-sm">
            Zip
            <input
              aria-label="Zip"
              maxLength={5}
              className="h-9 w-24 rounded-md border border-neutral-200 px-2 text-sm"
              value={draft.zip}
              onChange={(e) => setDraft((d) => ({ ...d, zip: e.target.value }))}
            />
          </label>
        </div>
        <label className="flex flex-col gap-1 text-sm">
          Own / rent
          <select
            aria-label="Own / rent"
            className="h-9 rounded-md border border-neutral-200 px-2 text-sm"
            value={draft.housing_status}
            onChange={(e) =>
              setDraft((d) => ({
                ...d,
                housing_status: e.target.value as HousingCreate["housing_status"],
              }))
            }
          >
            {HOUSING_STATUS_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </label>
        <div className="flex gap-3">
          <label className="flex flex-col gap-1 text-sm">
            Years at address
            <input
              aria-label="Years at address"
              type="number"
              min={0}
              max={80}
              className="h-9 w-24 rounded-md border border-neutral-200 px-2 text-sm"
              value={draft.residence_years}
              onChange={(e) => setDraft((d) => ({ ...d, residence_years: Number(e.target.value) }))}
            />
          </label>
          <label className="flex flex-col gap-1 text-sm">
            Months at address
            <input
              aria-label="Months at address"
              type="number"
              min={0}
              max={11}
              className="h-9 w-24 rounded-md border border-neutral-200 px-2 text-sm"
              value={draft.residence_months}
              onChange={(e) =>
                setDraft((d) => ({ ...d, residence_months: Number(e.target.value) }))
              }
            />
          </label>
        </div>
        <label className="flex items-center gap-2 text-sm">
          <input
            aria-label="VOM completed"
            type="checkbox"
            checked={draft.vom_completed ?? false}
            onChange={(e) => setDraft((d) => ({ ...d, vom_completed: e.target.checked }))}
          />
          VOM completed
        </label>

        {error && <p className="text-xs text-status-danger">{error}</p>}

        <div className="flex gap-2">
          <Button onClick={() => void submit()} isLoading={submitting}>
            Save
          </Button>
          <Button
            variant="ghost"
            disabled={submitting}
            onClick={() => {
              setDraft(EMPTY_DRAFT);
              setError(null);
              onOpenChange(false);
            }}
          >
            Cancel
          </Button>
        </div>
      </div>
    </Card>
  );
}
