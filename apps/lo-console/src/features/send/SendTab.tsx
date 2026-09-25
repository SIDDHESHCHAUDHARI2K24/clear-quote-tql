"use client";

import { useCallback } from "react";

import { useWorkspace } from "../workspace";
import { LoNoteField } from "./LoNoteField";
import { PreviewPanel } from "./PreviewPanel";
import { QuoteChecklist } from "./QuoteChecklist";
import { ReadinessList } from "./ReadinessList";
import { SendButton } from "./SendButton";
import { SendToast } from "./SendToast";
import { SentVersions } from "./SentVersions";
import { useSendFlow } from "./useSendFlow";
import { SEND_IN_PROGRESS_MESSAGE, useSendTab } from "./useSendTab";

/** Tab 7 (system-design.md "Send"): pick the quotes, confirm the
 * recommendation, preview exactly what the borrower gets, send. */
export function SendTab() {
  const { refetch: refetchWorkspace } = useWorkspace();
  const {
    applicationId,
    load,
    previews,
    saving,
    saveError,
    update,
    retrySave,
    reload,
    sendInProgressSignal,
  } = useSendTab();
  const packageId = load.kind === "ready" ? load.pkg.id : null;
  const onSent = useCallback(() => {
    // Status pill → Sent, and the package's `sent_at`.
    void refetchWorkspace();
    void reload();
  }, [refetchWorkspace, reload]);
  // A PUT refused with SEND_IN_PROGRESS re-reads the send status.
  const flow = useSendFlow(packageId, { onSent, resyncKey: sendInProgressSignal });

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
  // No edits while a send runs: the API refuses them (SEND_IN_PROGRESS).
  const locked = flow.inFlight;

  return (
    <div className="grid gap-6 lg:grid-cols-[minmax(320px,400px)_1fr]">
      <div className="flex flex-col gap-5">
        <QuoteChecklist pkg={pkg} scenarios={scenarios} disabled={locked} onChange={update} />

        <section className="flex flex-col gap-1" aria-label="What we recommend">
          <h3 className="text-sm font-semibold text-navy-900">What we recommend</h3>
          <p className="text-sm text-navy-900" data-testid="recommendation-text">
            {pkg.recommendation_text ?? "Pick a recommended quote."}
          </p>
        </section>

        <LoNoteField
          key={`${pkg.id}:${pkg.lo_note ?? ""}`}
          value={pkg.lo_note ?? ""}
          disabled={locked}
          onSave={(note) =>
            update({
              quote_ids: pkg.quote_ids,
              recommended_quote_id: pkg.recommended_quote_id ?? null,
              lo_note: note,
            })
          }
        />

        <div className="flex flex-wrap items-center gap-2">
          <p className="text-xs text-neutral-600" aria-live="polite" data-testid="save-status">
            {saving ? "Saving…" : saveError ? saveError : "All changes saved"}
          </p>
          {!saving && saveError && saveError !== SEND_IN_PROGRESS_MESSAGE && !locked && (
            <button
              type="button"
              onClick={() => void retrySave()}
              className="text-xs font-medium text-navy-700 underline"
            >
              Retry
            </button>
          )}
        </div>

        <ReadinessList applicationId={applicationId} readiness={readiness} />
        <div className="flex flex-col items-start gap-1">
          <SendButton
            pkg={pkg}
            readiness={readiness}
            phase={flow.phase}
            onSend={() => void flow.start()}
            onReset={flow.reset}
          />
        </div>
        <SentVersions versions={flow.versions} />
      </div>
      <PreviewPanel report={previews.report} letter={previews.letter} />
      <SendToast message={flow.toast} onDismiss={flow.dismissToast} />
    </div>
  );
}
