"use client";

import { useState } from "react";
import type { ChangeEvent, FormEvent } from "react";

import { Button, Card, EmptyState } from "@cq/ui";

import {
  FieldRow,
  FlagList,
  addParty,
  putField,
  revertField,
  runSectionAction,
  useSection,
} from "../shared";
import type {
  FieldRowKind,
  FieldRowOption,
  PartyCreate,
  SectionField,
  SectionFlag,
  SectionRecord,
  SectionResponse,
} from "../shared";
import { SsnField } from "./SsnField";

// Field order + edit widget for every suffix on a party record except `ssn`
// (bespoke `SsnField`, reveal + edit) and `no_co_applicant_check` (only
// surfaced on the primary borrower's card, via `NoCoApplicantSection`
// below) -- see the CQ-028b "Borrowers tab" build spec's field table.
const SUFFIX_CONFIG: Record<string, { kind: FieldRowKind; options?: FieldRowOption[] }> = {
  first_name: { kind: "text" },
  last_name: { kind: "text" },
  dob: { kind: "date" },
  marital_status: {
    kind: "select",
    options: [
      { value: "married", label: "Married" },
      { value: "unmarried", label: "Unmarried" },
      { value: "separated", label: "Separated" },
    ],
  },
  dependents_count: { kind: "number" },
  email: { kind: "text" },
  cell_phone: { kind: "text" },
  home_phone: { kind: "text" },
  work_phone: { kind: "text" },
  business_vesting: {
    kind: "select",
    options: [
      { value: "personal_name", label: "Personal name" },
      { value: "title_lien_in_llc", label: "Title/lien in LLC" },
    ],
  },
  llc_entity_name: { kind: "text" },
};

function suffixOf(fieldKey: string, role: string): string {
  return fieldKey.startsWith(`${role}_`) ? fieldKey.slice(role.length + 1) : fieldKey;
}

interface PartyCardProps {
  applicationId: string;
  record: SectionRecord;
  flagsByKey: Map<string, SectionFlag>;
  applyResult: (section: SectionResponse) => void;
}

function PartyCard({ applicationId, record, flagsByKey, applyResult }: PartyCardProps) {
  const role = record.role ?? "borrower";
  const title = role === "borrower" ? "Borrower" : "Co-borrower";
  const partyId = record.id;

  return (
    <Card title={title}>
      <div className="flex flex-col">
        {record.fields.map((field) => {
          const suffix = suffixOf(field.field_key, role);
          if (suffix === "no_co_applicant_check") return null;
          const flag = flagsByKey.get(field.field_key);

          if (suffix === "ssn") {
            return (
              <SsnField
                key={field.field_key}
                applicationId={applicationId}
                partyId={partyId}
                field={field}
                flag={flag}
                applyResult={applyResult}
              />
            );
          }

          const config = SUFFIX_CONFIG[suffix] ?? { kind: "text" as const };
          return (
            <FieldRow
              key={field.field_key}
              field={field}
              flag={flag}
              kind={config.kind}
              options={config.options}
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

interface NoCoApplicantCheckboxProps {
  applicationId: string;
  field: SectionField;
  applyResult: (section: SectionResponse) => void;
}

function NoCoApplicantCheckbox({ applicationId, field, applyResult }: NoCoApplicantCheckboxProps) {
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const checked = field.value === true;

  const toggle = async () => {
    setSaving(true);
    setError(null);
    const result = await runSectionAction(() => putField(applicationId, field.field_key, !checked));
    if (!result.ok) {
      setError(result.message);
    } else {
      applyResult(result.section);
    }
    setSaving(false);
  };

  return (
    <label className="flex items-center gap-2 text-sm text-navy-900">
      <input
        type="checkbox"
        checked={checked}
        disabled={saving}
        onChange={() => void toggle()}
        aria-label="No co-applicant"
      />
      No co-applicant
      {error && <span className="text-xs text-status-danger">{error}</span>}
    </label>
  );
}

interface AddCoBorrowerFormProps {
  applicationId: string;
  applyResult: (section: SectionResponse) => void;
  onDone: () => void;
}

interface AddCoBorrowerValues {
  first_name: string;
  last_name: string;
  ssn: string;
  dob: string;
  email: string;
  cell_phone: string;
  home_phone: string;
  work_phone: string;
}

const EMPTY_ADD_VALUES: AddCoBorrowerValues = {
  first_name: "",
  last_name: "",
  ssn: "",
  dob: "",
  email: "",
  cell_phone: "",
  home_phone: "",
  work_phone: "",
};

function AddCoBorrowerForm({ applicationId, applyResult, onDone }: AddCoBorrowerFormProps) {
  const [values, setValues] = useState<AddCoBorrowerValues>(EMPTY_ADD_VALUES);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const update = (key: keyof AddCoBorrowerValues) => (e: ChangeEvent<HTMLInputElement>) =>
    setValues((prev) => ({ ...prev, [key]: e.target.value }));

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (!values.first_name.trim() || !values.last_name.trim()) {
      setError("First and last name are required.");
      return;
    }
    setSaving(true);
    setError(null);
    const body: PartyCreate = {
      first_name: values.first_name.trim(),
      last_name: values.last_name.trim(),
      ssn: values.ssn.trim() || undefined,
      dob: values.dob.trim() || undefined,
      email: values.email.trim() || undefined,
      cell_phone: values.cell_phone.trim() || undefined,
      home_phone: values.home_phone.trim() || undefined,
      work_phone: values.work_phone.trim() || undefined,
    };
    const result = await runSectionAction(() => addParty(applicationId, body));
    setSaving(false);
    if (!result.ok) {
      setError(result.message);
      return;
    }
    applyResult(result.section);
    onDone();
  };

  const inputClass = "h-9 rounded-md border border-neutral-200 px-2 text-sm";
  const labelClass = "flex flex-col gap-1 text-xs font-medium text-neutral-600";

  return (
    <form
      onSubmit={(e) => void submit(e)}
      className="mt-3 flex flex-col gap-3 rounded-md border border-neutral-200 p-3"
    >
      <div className="grid grid-cols-2 gap-3">
        <label className={labelClass}>
          First name
          <input
            className={inputClass}
            value={values.first_name}
            onChange={update("first_name")}
            required
          />
        </label>
        <label className={labelClass}>
          Last name
          <input
            className={inputClass}
            value={values.last_name}
            onChange={update("last_name")}
            required
          />
        </label>
        <label className={labelClass}>
          SSN
          <input className={inputClass} value={values.ssn} onChange={update("ssn")} />
        </label>
        <label className={labelClass}>
          Date of birth
          <input type="date" className={inputClass} value={values.dob} onChange={update("dob")} />
        </label>
        <label className={labelClass}>
          Email
          <input className={inputClass} value={values.email} onChange={update("email")} />
        </label>
        <label className={labelClass}>
          Cell phone
          <input className={inputClass} value={values.cell_phone} onChange={update("cell_phone")} />
        </label>
        <label className={labelClass}>
          Home phone
          <input className={inputClass} value={values.home_phone} onChange={update("home_phone")} />
        </label>
        <label className={labelClass}>
          Work phone
          <input className={inputClass} value={values.work_phone} onChange={update("work_phone")} />
        </label>
      </div>
      {error && <p className="text-xs text-status-danger">{error}</p>}
      <div className="flex gap-2">
        <Button type="submit" isLoading={saving} size="sm">
          Add co-borrower
        </Button>
        <Button type="button" variant="ghost" size="sm" onClick={onDone} disabled={saving}>
          Cancel
        </Button>
      </div>
    </form>
  );
}

interface NoCoApplicantSectionProps {
  applicationId: string;
  borrower: SectionRecord;
  applyResult: (section: SectionResponse) => void;
  showAddForm: boolean;
  setShowAddForm: (value: boolean) => void;
}

function NoCoApplicantSection({
  applicationId,
  borrower,
  applyResult,
  showAddForm,
  setShowAddForm,
}: NoCoApplicantSectionProps) {
  const noCoField = borrower.fields.find(
    (field) => field.field_key === "borrower_no_co_applicant_check",
  );
  const checked = noCoField?.value === true;

  if (checked) {
    return (
      <Card title="Co-borrower">
        <div className="flex flex-col gap-2">
          <p className="text-sm text-navy-900">No co-applicant</p>
          {noCoField && (
            <NoCoApplicantCheckbox
              applicationId={applicationId}
              field={noCoField}
              applyResult={applyResult}
            />
          )}
        </div>
      </Card>
    );
  }

  return (
    <div className="flex flex-col gap-3">
      <EmptyState
        title="No co-borrower yet"
        body="Add a co-borrower, or mark this application as having no co-applicant."
        action={
          <div className="flex flex-col items-center gap-3">
            <Button
              type="button"
              variant="secondary"
              size="sm"
              onClick={() => setShowAddForm(!showAddForm)}
            >
              Add co-borrower
            </Button>
            {noCoField && (
              <NoCoApplicantCheckbox
                applicationId={applicationId}
                field={noCoField}
                applyResult={applyResult}
              />
            )}
          </div>
        }
      />
      {showAddForm && (
        <AddCoBorrowerForm
          applicationId={applicationId}
          applyResult={applyResult}
          onDone={() => setShowAddForm(false)}
        />
      )}
    </div>
  );
}

export function BorrowersTab({ applicationId }: { applicationId: string }) {
  const { state, refetch, applyResult } = useSection(applicationId, "borrowers");
  const [showAddForm, setShowAddForm] = useState(false);

  if (state.kind === "loading") {
    return <p className="px-6 py-4 text-sm text-neutral-600">Loading…</p>;
  }
  if (state.kind === "error") {
    return (
      <div className="px-6 py-4">
        <p className="text-sm text-status-danger">Couldn&apos;t load this tab.</p>
        <button type="button" className="text-sm underline" onClick={() => refetch()}>
          Retry
        </button>
      </div>
    );
  }

  const { section } = state;
  const flagsByKey = new Map(section.flags.map((flag) => [flag.field_key, flag]));
  const partyRecords = section.records.filter((record) => record.kind === "party");
  const borrower = partyRecords.find((record) => record.role === "borrower");
  const coBorrower = partyRecords.find((record) => record.role === "co_borrower");

  return (
    <div className="flex flex-col gap-4 px-6 py-4">
      <FlagList flags={section.flags} />
      {partyRecords.map((record) => (
        <PartyCard
          key={record.id ?? record.role ?? "party"}
          applicationId={applicationId}
          record={record}
          flagsByKey={flagsByKey}
          applyResult={applyResult}
        />
      ))}
      {!coBorrower && borrower && (
        <NoCoApplicantSection
          applicationId={applicationId}
          borrower={borrower}
          applyResult={applyResult}
          showAddForm={showAddForm}
          setShowAddForm={setShowAddForm}
        />
      )}
    </div>
  );
}
