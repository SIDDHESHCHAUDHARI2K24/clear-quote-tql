"use client";

import { useState } from "react";

import { Button, Card, extractErrorMessage, formatDate, formatMoneyPrecise } from "@cq/ui";

import {
  FieldRow,
  FlagList,
  fieldBySuffix,
  formatDtiRatio,
  importLiabilities,
  putField,
  requestHardPull,
  revertField,
  runSectionAction,
  useSection,
} from "../shared";
import type { CreditSummary, SectionFlag, SectionRecord, UseSectionResult } from "../shared";

// Order + kind for a liability row's fixed fields (real `field_key` is
// `liabilities.{row_id}.{suffix}`, per the coordinator's brief).
const LIABILITY_FIELD_SPECS: Array<{ suffix: string; kind: "text" | "money" }> = [
  { suffix: "creditor_name", kind: "text" },
  { suffix: "account_type", kind: "text" },
  { suffix: "monthly_payment", kind: "money" },
  { suffix: "balance", kind: "money" },
];

export function CreditTab({ applicationId }: { applicationId: string }) {
  const { state, refetch, applyResult } = useSection(applicationId, "credit");

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
  const credit = section.credit; // CreditSummary | null | undefined -- guard, though it should always be set on this tab
  const flagsByKey = new Map(section.flags.map((flag) => [flag.field_key, flag]));
  // The "credit" kind record (representative_fico/credit_score_bracket) just
  // duplicates section.credit, which CreditSummaryCard renders directly --
  // only liability rows get their own Card of FieldRows.
  const liabilityRecords = section.records.filter((record) => record.kind === "liability");

  return (
    <div className="flex flex-col gap-4 px-6 py-4">
      <FlagList flags={section.flags} />

      {credit && <CreditSummaryCard credit={credit} />}

      <div className="flex flex-wrap gap-3">
        <ImportLiabilitiesButton applicationId={applicationId} applyResult={applyResult} />
        <RequestHardPullButton
          applicationId={applicationId}
          credit={credit}
          applyResult={applyResult}
        />
      </div>

      {liabilityRecords.map((record) => (
        <LiabilityCard
          // `service.py` always sets a real row id on a `liability` record
          // (react-doctor/no-array-index-as-key).
          key={record.id as string}
          applicationId={applicationId}
          record={record}
          flagsByKey={flagsByKey}
          applyResult={applyResult}
        />
      ))}
    </div>
  );
}

/** Representative FICO + bracket, pull type/date, liabilities total, DTI
 * (primary only, AC8) and the hard-pull consent state (E11). */
function CreditSummaryCard({ credit }: { credit: CreditSummary }) {
  return (
    <Card title="Credit">
      <div className="flex flex-col gap-2 text-sm text-navy-900">
        <div>
          <span className="font-medium">FICO: </span>
          {credit.representative_fico ?? "—"}
          {credit.fico_bracket ? ` (${credit.fico_bracket})` : ""}
        </div>
        <div>
          <span className="font-medium">Pull: </span>
          {credit.pull_type === "hard_pull"
            ? "Hard pull"
            : credit.pull_type === "soft_pull"
              ? "Soft pull"
              : "—"}
          {credit.pulled_at ? ` on ${formatDate(credit.pulled_at.slice(0, 10))}` : ""}
        </div>
        <div>
          <span className="font-medium">Liabilities total: </span>
          {formatMoneyPrecise(credit.liabilities_monthly_total)}
        </div>
        {credit.dti_applicable && <DtiRow credit={credit} />}
        <ConsentRow consent={credit.consent} />
      </div>
    </Card>
  );
}

// AC8: DTI only ever renders when dti_applicable is true (the API's own
// primary/investment gate -- never section.occupancy).
function DtiRow({ credit }: { credit: CreditSummary }) {
  let text: string;
  if (credit.dti_status === "ok" && credit.dti) {
    text = formatDtiRatio(credit.dti);
  } else if (credit.dti_status === "awaiting_pricing") {
    text = "Awaiting pricing";
  } else if (credit.dti_status === "no_income") {
    text = "No income on file";
  } else {
    text = "—";
  }
  return (
    <div>
      <span className="font-medium">DTI: </span>
      {text}
    </div>
  );
}

// E11 -- exact wording from spec.md's Credit tab bullet. `consent === null`
// (never requested) renders nothing here; the "Request hard pull" button
// covers that state on its own.
function ConsentRow({ consent }: { consent: CreditSummary["consent"] }) {
  if (!consent) return null;

  let text: string | null = null;
  if (consent.status === "pending") {
    text = "Awaiting borrower consent";
  } else if (consent.status === "accepted") {
    const date = consent.decided_at ? formatDate(consent.decided_at.slice(0, 10)) : "—";
    text = `Authorized ${date} — hard pull complete, FICO ${consent.fico_after_pull ?? "—"}`;
  } else if (consent.status === "declined") {
    const date = consent.decided_at ? formatDate(consent.decided_at.slice(0, 10)) : "—";
    text = `Declined ${date}: ${consent.decline_reason ?? "—"}`;
  } else if (consent.status === "expired") {
    const date = consent.expires_at ? formatDate(consent.expires_at.slice(0, 10)) : "—";
    text = `Expired ${date}`;
  }
  if (!text) return null;

  return (
    <div>
      <span className="font-medium">Consent: </span>
      {text}
    </div>
  );
}

/** AC4's "Import liabilities" -- replaces imported rows, keeps manual ones
 * (backend behavior; this only wires the button + error). */
function ImportLiabilitiesButton({
  applicationId,
  applyResult,
}: {
  applicationId: string;
  applyResult: UseSectionResult["applyResult"];
}) {
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const run = async () => {
    setSubmitting(true);
    setError(null);
    const result = await runSectionAction(
      () => importLiabilities(applicationId),
      "Could not import liabilities.",
    );
    setSubmitting(false);
    if (!result.ok) {
      setError(result.message);
      return;
    }
    applyResult(result.section);
  };

  return (
    <div className="flex flex-col gap-1">
      <Button variant="secondary" onClick={() => void run()} isLoading={submitting}>
        Import liabilities
      </Button>
      {error && <p className="text-xs text-status-danger">{error}</p>}
    </div>
  );
}

/** AC5's "Request hard pull" -- `requestHardPull` isn't wrapped by
 * `runSectionAction` (its data shape is `{consent, section}`), so this
 * handles the `{data, error}` result directly. Disabled while a request is
 * already pending; a 409 (e.g. a race) still surfaces inline via
 * `extractErrorMessage`. */
function RequestHardPullButton({
  applicationId,
  credit,
  applyResult,
}: {
  applicationId: string;
  credit: CreditSummary | null | undefined;
  applyResult: UseSectionResult["applyResult"];
}) {
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const pending = credit?.consent?.status === "pending";

  const run = async () => {
    setSubmitting(true);
    setError(null);
    try {
      const { data, error: err } = await requestHardPull(applicationId);
      if (!data) {
        setError(extractErrorMessage(err, "Could not request a hard pull."));
        return;
      }
      applyResult(data.section);
    } catch {
      setError("Network error. Try again.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="flex flex-col gap-1">
      <Button
        variant="secondary"
        onClick={() => void run()}
        isLoading={submitting}
        disabled={pending}
      >
        Request hard pull
      </Button>
      {error && <p className="text-xs text-status-danger">{error}</p>}
    </div>
  );
}

function LiabilityCard({
  applicationId,
  record,
  flagsByKey,
  applyResult,
}: {
  applicationId: string;
  record: SectionRecord;
  flagsByKey: Map<string, SectionFlag>;
  applyResult: UseSectionResult["applyResult"];
}) {
  const creditorField = fieldBySuffix(record, "creditor_name");
  const title = (typeof creditorField?.value === "string" && creditorField.value) || "Liability";

  return (
    <Card title={title}>
      <div className="flex flex-col">
        {LIABILITY_FIELD_SPECS.map(({ suffix, kind }) => {
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
