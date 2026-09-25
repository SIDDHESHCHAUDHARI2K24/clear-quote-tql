"use client";

import { LoNoteField } from "./LoNoteField";
import { PreviewPanel } from "./PreviewPanel";
import { QuoteChecklist } from "./QuoteChecklist";
import { ReadinessList } from "./ReadinessList";
import { SendButton } from "./SendButton";
import { useSendTab } from "./useSendTab";

/** Tab 7 (system-design.md "Send"): pick the quotes, confirm the
 * recommendation, preview exactly what the borrower gets, send. */
export function SendTab() {
  const { applicationId, load, previews, saving, saveError, update } = useSendTab();

  if (load.kind === "loading") {
    return <p className="text-sm text-neutral-600">Loading the quote package…</p>;
  }
  if (load.kind === "error") {
    return (
      <p role="alert" className="text-sm text-status-danger">
        {load.message}
      </p>
    );
  }

  const { pkg, scenarios } = load;
  const readiness = previews.readiness?.ok ? previews.readiness.data : null;

  return (
    <div className="grid gap-6 lg:grid-cols-[minmax(320px,400px)_1fr]">
      <div className="flex flex-col gap-5">
        <QuoteChecklist pkg={pkg} scenarios={scenarios} onChange={update} />

        <section className="flex flex-col gap-1" aria-label="What we recommend">
          <h3 className="text-sm font-semibold text-navy-900">What we recommend</h3>
          <p className="text-sm text-navy-900" data-testid="recommendation-text">
            {pkg.recommendation_text ?? "Pick a recommended quote."}
          </p>
        </section>

        <LoNoteField
          key={`${pkg.id}:${pkg.lo_note ?? ""}`}
          value={pkg.lo_note ?? ""}
          onSave={(note) =>
            update({
              quote_ids: pkg.quote_ids,
              recommended_quote_id: pkg.recommended_quote_id ?? null,
              lo_note: note,
            })
          }
        />

        <p className="text-xs text-neutral-600" aria-live="polite" data-testid="save-status">
          {saving ? "Saving…" : saveError ? saveError : "All changes saved"}
        </p>

        <ReadinessList applicationId={applicationId} readiness={readiness} />
        <div className="flex flex-col items-start gap-1">
          <SendButton pkg={pkg} readiness={readiness} />
        </div>
      </div>
      <PreviewPanel report={previews.report} letter={previews.letter} />
    </div>
  );
}
