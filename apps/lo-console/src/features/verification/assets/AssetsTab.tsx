"use client";

import { useState } from "react";

import { Button, Card, formatDate, formatMoneyPrecise } from "@cq/ui";

import {
  FieldRow,
  FlagList,
  fieldBySuffix,
  patchDocument,
  putField,
  revertField,
  runSectionAction,
  useSection,
} from "../shared";
import type {
  AssetsSummary,
  DocumentItem,
  SectionFlag,
  SectionRecord,
  UseSectionResult,
} from "../shared";

// Order + kind for each record kind's fixed fields (coordinator's tab spec,
// docs/backlog/CQ-028-verification-tabs/spec.md row 4 "Assets & income" --
// suffix matches the backend's `assets.{row_id}.{suffix}` /
// `employment.{row_id}.{suffix}` field_key exactly).
const ASSET_FIELD_SPECS: Array<{ suffix: string; kind: "text" | "money" }> = [
  { suffix: "account_type", kind: "text" },
  { suffix: "institution", kind: "text" },
  { suffix: "verified_amount", kind: "money" },
];

const EMPLOYMENT_FIELD_SPECS: Array<{ suffix: string; kind: "text" | "money" | "boolean" }> = [
  { suffix: "employer_name", kind: "text" },
  { suffix: "monthly_income", kind: "money" },
  { suffix: "self_employed", kind: "boolean" },
];

export function AssetsTab({ applicationId }: { applicationId: string }) {
  const { state, refetch, applyResult } = useSection(applicationId, "assets");

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
  const assets = section.assets;
  const flagsByKey = new Map(section.flags.map((flag) => [flag.field_key, flag]));
  const assetRecords = section.records.filter((record) => record.kind === "asset");
  const employmentRecords = section.records.filter((record) => record.kind === "employment");

  return (
    <div className="flex flex-col gap-4 px-6 py-4">
      <FlagList flags={section.flags} />

      {assets && <AssetsSummaryBanner assets={assets} />}

      {assetRecords.map((record, index) => (
        <RecordCard
          // `service.py` always sets a real row id on an `asset` record
          // (react-doctor/no-array-index-as-key); `index` below is only
          // used for the fallback title text, not the key.
          key={record.id as string}
          applicationId={applicationId}
          record={record}
          fallbackTitle={`Asset ${index + 1}`}
          titleSuffixes={["account_type", "institution"]}
          fieldSpecs={ASSET_FIELD_SPECS}
          flagsByKey={flagsByKey}
          applyResult={applyResult}
        />
      ))}

      {assets?.income_applicable && (
        <>
          {employmentRecords.map((record, index) => (
            <RecordCard
              // Same as the asset records above: `id` is always real here.
              key={record.id as string}
              applicationId={applicationId}
              record={record}
              fallbackTitle={`Employment ${index + 1}`}
              titleSuffixes={["employer_name"]}
              fieldSpecs={EMPLOYMENT_FIELD_SPECS}
              flagsByKey={flagsByKey}
              applyResult={applyResult}
            />
          ))}
          <MonthlyIncomeSummary monthlyIncomeTotal={assets.monthly_income_total} />
        </>
      )}

      {assets && (
        <DocumentChecklist
          applicationId={applicationId}
          documents={assets.documents}
          applyResult={applyResult}
        />
      )}
    </div>
  );
}

const STATUS_LABEL: Record<AssetsSummary["status"], string> = {
  sufficient: "Sufficient",
  insufficient: "Insufficient",
  awaiting_pricing: "Awaiting pricing",
};

const STATUS_CLASSES: Record<AssetsSummary["status"], string> = {
  sufficient: "border-status-success bg-status-success/5 text-status-success",
  insufficient: "border-status-danger bg-status-danger/5 text-status-danger",
  awaiting_pricing: "border-neutral-200 bg-neutral-50 text-neutral-600",
};

/** Verified assets total, reserves required (6 months PITIA) and the
 * sufficiency check (spec.md row 4 "Assets & income"). `reserves_required`,
 * `cash_to_close` and `required_funds` are `null` until a quote exists --
 * this only formats what the backend already computed, it never does the
 * money math itself. */
function AssetsSummaryBanner({ assets }: { assets: AssetsSummary }) {
  const { reserves_months, reserves_required, required_funds, cash_to_close, status } = assets;
  return (
    <Card title="Assets summary">
      <div className="flex flex-col gap-2 text-sm">
        <p className="text-navy-900">
          Verified assets total:{" "}
          <span className="font-semibold">{formatMoneyPrecise(assets.verified_assets_total)}</span>
        </p>
        <p className="text-navy-900">
          Reserves required: {reserves_months} months (
          {reserves_required !== null ? formatMoneyPrecise(reserves_required) : "Awaiting pricing"})
        </p>
        <p className="text-navy-900">
          Cash to close:{" "}
          {cash_to_close !== null ? formatMoneyPrecise(cash_to_close) : "Awaiting pricing"}
        </p>
        <p className="text-navy-900">
          Required funds:{" "}
          {required_funds !== null ? formatMoneyPrecise(required_funds) : "Awaiting pricing"}
        </p>
        <div
          role="status"
          className={`rounded-md border-l-4 px-3 py-2 text-sm font-semibold ${STATUS_CLASSES[status]}`}
        >
          {STATUS_LABEL[status]}
        </div>
      </div>
    </Card>
  );
}

/** AC8: employment and income only render for primary loans -- gated by the
 * caller on `assets.income_applicable`, mirroring the DTI gate on the Credit
 * tab. `monthly_income_total` is a decimal string, formatted only. */
function MonthlyIncomeSummary({ monthlyIncomeTotal }: { monthlyIncomeTotal: string | null }) {
  if (monthlyIncomeTotal === null) return null;
  return (
    <p className="text-sm font-medium text-navy-900">
      Total monthly income: {formatMoneyPrecise(monthlyIncomeTotal)}
    </p>
  );
}

function RecordCard({
  applicationId,
  record,
  fallbackTitle,
  titleSuffixes,
  fieldSpecs,
  flagsByKey,
  applyResult,
}: {
  applicationId: string;
  record: SectionRecord;
  fallbackTitle: string;
  titleSuffixes: string[];
  fieldSpecs: Array<{ suffix: string; kind: "text" | "money" | "boolean" }>;
  flagsByKey: Map<string, SectionFlag>;
  applyResult: UseSectionResult["applyResult"];
}) {
  const titleParts = titleSuffixes
    .map((suffix) => fieldBySuffix(record, suffix)?.value)
    .filter((value): value is string => typeof value === "string" && value.length > 0);
  const title = titleParts.length > 0 ? titleParts.join(" — ") : fallbackTitle;

  return (
    <Card title={title}>
      <div className="flex flex-col">
        {fieldSpecs.map(({ suffix, kind }) => {
          const field = fieldBySuffix(record, suffix);
          if (!field) return null;
          return (
            <FieldRow
              key={field.field_key}
              field={field}
              flag={flagsByKey.get(field.field_key)}
              kind={kind}
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

/** The document checklist's "Mark received" / "Mark not received" action
 * (spec.md row 4's LO action). `patchDocument` doesn't carry a `resume`
 * field -- it doesn't re-verify -- so no toast fires from this, which is
 * correct/expected (coordinator's briefing). */
function DocumentChecklist({
  applicationId,
  documents,
  applyResult,
}: {
  applicationId: string;
  documents: DocumentItem[];
  applyResult: UseSectionResult["applyResult"];
}) {
  return (
    <Card title="Document checklist">
      <ul className="flex flex-col gap-2">
        {documents.map((doc) => (
          <DocumentRow
            key={doc.id}
            applicationId={applicationId}
            doc={doc}
            applyResult={applyResult}
          />
        ))}
        {documents.length === 0 && (
          <li className="text-sm text-neutral-600">No documents required.</li>
        )}
      </ul>
    </Card>
  );
}

function DocumentRow({
  applicationId,
  doc,
  applyResult,
}: {
  applicationId: string;
  doc: DocumentItem;
  applyResult: UseSectionResult["applyResult"];
}) {
  const label = doc.doc_type.replace(/_/g, " ");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const toggle = async () => {
    setSaving(true);
    setError(null);
    const result = await runSectionAction(() =>
      patchDocument(applicationId, doc.id, !doc.received),
    );
    setSaving(false);
    if (!result.ok) {
      setError(result.message);
      return;
    }
    applyResult(result.section);
  };

  return (
    <li className="flex flex-wrap items-center justify-between gap-2 border-b border-neutral-100 py-2 last:border-0">
      <div className="flex flex-col">
        <span className="text-sm font-medium capitalize text-navy-900">{label}</span>
        {doc.received && doc.received_at && (
          <span className="text-xs text-neutral-600">
            Received {formatDate(doc.received_at.slice(0, 10))}
          </span>
        )}
        {error && <span className="text-xs text-status-danger">{error}</span>}
      </div>
      <Button
        variant={doc.received ? "secondary" : "primary"}
        size="sm"
        isLoading={saving}
        onClick={() => void toggle()}
      >
        {doc.received ? "Mark not received" : "Mark received"}
      </Button>
    </li>
  );
}
