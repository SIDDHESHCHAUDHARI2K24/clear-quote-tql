"use client";

import { useState } from "react";

import { Button, extractErrorMessage, formatDate } from "@cq/ui";
import type { ReportOptionData, ReportViewModelData } from "@cq/ui";

import { AskOtherDialog } from "../actions/AskOtherDialog";
import { MoveForwardDialog } from "../actions/MoveForwardDialog";
import type { BorrowerActionRecord } from "../actions/api";
import { submitReportAction } from "../actions/api";

export interface ReportActionsSlotProps {
  viewModel: ReportViewModelData;
  selectedOption: ReportOptionData;
  /** The report's link token -- what the action POSTs against. */
  token: string;
  /** `PortalReportResponse.borrower_action`, parsed (CQ-024 plan.md
   * Decision 1: the version's JSONB is the source of truth). `null` until
   * an action has been taken on this version. */
  borrowerAction: BorrowerActionRecord | null;
  /** Re-fetches `/portal/reports/{token}` and applies the fresh response
   * (`ReportView.tsx`'s `loadReport`). Called after every successful
   * action and on a 409, so this slot never has to guess the current
   * state itself (plan.md Decision 8). */
  onActionTaken: () => void;
}

function firstName(fullName: string): string {
  return fullName.trim().split(/\s+/)[0] ?? fullName;
}

/** `borrowerAction.at` is a full ISO datetime (`now.isoformat()`,
 * service.py); `@cq/ui`'s `formatDate` (packages/ui/src/report/format.ts)
 * expects a bare `YYYY-MM-DD` date and formats it pinned to UTC, so the
 * rendered string can never differ between the server-rendered and
 * hydrated client (react-doctor's `no-locale-format-in-render` --
 * `toLocaleDateString(undefined, ...)` uses the runtime's own locale,
 * which can legitimately differ between server and browser). Slicing to
 * the date portion reuses that instead of a second, locale-dependent
 * formatter. */
function formatActionDate(iso: string): string {
  return formatDate(iso.slice(0, 10));
}

type DialogState = { kind: "none" } | { kind: "move_forward" } | { kind: "ask_other" };

/**
 * Borrower actions (system-design.md "Quote report" page order step 9):
 * "I'd like to move forward with this option" and "Ask about another
 * option" -- both non-binding (Decision 5), never "Accept" and never a
 * locked rate. Wired into `ReportPage`'s `renderActions` prop from
 * `apps/borrower-portal/src/app/report/[token]/page.tsx` via
 * `ReportView.tsx` (plan.md Decision D3/8) -- `ReportPage` itself already
 * wraps this slot's output in a `print:hidden` container.
 */
export function ReportActionsSlot({
  viewModel,
  selectedOption,
  token,
  borrowerAction,
  onActionTaken,
}: ReportActionsSlotProps) {
  const [dialog, setDialog] = useState<DialogState>({ kind: "none" });
  // Bumped on every "Ask about another option" click and passed to
  // AskOtherDialog as its `key`, so React remounts it fresh (blank
  // message) each time instead of an effect reconciling stale state --
  // see AskOtherDialog's own docstring.
  const [askOtherOpenCount, setAskOtherOpenCount] = useState(0);
  const [submitting, setSubmitting] = useState(false);
  const [dialogError, setDialogError] = useState<string | null>(null);
  const [askUpdatedState, setAskUpdatedState] = useState<"idle" | "submitting" | "sent" | "error">(
    "idle",
  );
  const [notice, setNotice] = useState<string | null>(null);

  const loFirstName = firstName(viewModel.lo.name);

  // Superseded: the SupersededBanner (rendered elsewhere in ReportPage)
  // already links to the newest version -- actions on a stale version are
  // never shown here (CQ-022 review carry-over finding #2). The API 409s
  // this too, as defense in depth.
  if (viewModel.header.superseded) return null;

  const moveForwardConfirmed = borrowerAction?.type === "move_forward";

  async function runAction(
    body: {
      type: "move_forward" | "ask_other" | "ask_updated";
      quote_id?: string;
      message?: string;
    },
    opts: { onSuccess: () => void },
  ) {
    setSubmitting(true);
    setDialogError(null);
    try {
      const { error, response } = await submitReportAction(token, body);
      if (!error) {
        opts.onSuccess();
        onActionTaken();
        return;
      }
      if (response.status === 409) {
        // "409 shows the current state without an error-looking message"
        // -- close whatever dialog is open and refetch; the refetched
        // viewModel/borrowerAction drives this component back to the
        // correct state on its own.
        setDialog({ kind: "none" });
        onActionTaken();
        return;
      }
      setDialogError(extractErrorMessage(error, "Something went wrong. Try again."));
    } catch {
      setDialogError("Something went wrong. Try again.");
    } finally {
      setSubmitting(false);
    }
  }

  async function handleAskUpdated() {
    setAskUpdatedState("submitting");
    try {
      const { error, response } = await submitReportAction(token, { type: "ask_updated" });
      if (!error) {
        setAskUpdatedState("sent");
        onActionTaken();
        return;
      }
      if (response.status === 409) {
        setAskUpdatedState("idle");
        onActionTaken();
        return;
      }
      setAskUpdatedState("error");
    } catch {
      setAskUpdatedState("error");
    }
  }

  if (moveForwardConfirmed) {
    const chosenLabel =
      viewModel.options.find((o) => o.quote_id === borrowerAction?.quote_id)?.label ??
      selectedOption.label;
    return (
      <section aria-label="Actions" data-testid="actions-slot" className="flex flex-col gap-2">
        <p className="text-sm text-navy-900">
          You chose <strong>{chosenLabel}</strong> on {formatActionDate(borrowerAction!.at)}.{" "}
          {viewModel.lo.name} will be in touch.
        </p>
        <p className="text-sm text-neutral-600">
          {viewModel.lo.title} &middot; NMLS {viewModel.lo.nmls} &middot; {viewModel.lo.phone}{" "}
          &middot; {viewModel.lo.email}
        </p>
      </section>
    );
  }

  if (viewModel.header.expired) {
    return (
      <section
        aria-label="Actions"
        data-testid="actions-slot"
        data-selected-quote-id={selectedOption.quote_id}
        className="flex flex-col gap-2"
      >
        <Button
          type="button"
          variant="secondary"
          isLoading={askUpdatedState === "submitting"}
          onClick={handleAskUpdated}
        >
          Ask for updated numbers
        </Button>
        {askUpdatedState === "sent" && (
          <p className="text-sm text-neutral-600">
            Sent &mdash; {loFirstName} will follow up with updated numbers.
          </p>
        )}
        {askUpdatedState === "error" && (
          <p role="alert" className="text-sm text-status-danger">
            Something went wrong. Try again.
          </p>
        )}
      </section>
    );
  }

  return (
    <section
      aria-label="Actions"
      data-testid="actions-slot"
      data-selected-quote-id={selectedOption.quote_id}
      className="flex flex-col gap-3"
    >
      <div className="flex flex-col gap-3 sm:flex-row">
        <Button type="button" onClick={() => setDialog({ kind: "move_forward" })}>
          I&rsquo;d like to move forward with this option
        </Button>
        <Button
          type="button"
          variant="secondary"
          onClick={() => {
            setAskOtherOpenCount((count) => count + 1);
            setDialog({ kind: "ask_other" });
          }}
        >
          Ask about another option
        </Button>
      </div>
      {notice && <p className="text-sm text-neutral-600">{notice}</p>}

      <MoveForwardDialog
        isOpen={dialog.kind === "move_forward"}
        onClose={() => setDialog({ kind: "none" })}
        optionLabel={selectedOption.label}
        loFirstName={loFirstName}
        submitting={submitting}
        error={dialogError}
        onConfirm={() =>
          runAction(
            { type: "move_forward", quote_id: selectedOption.quote_id },
            {
              onSuccess: () => {
                setDialog({ kind: "none" });
                setNotice(null);
              },
            },
          )
        }
      />
      <AskOtherDialog
        key={askOtherOpenCount}
        isOpen={dialog.kind === "ask_other"}
        onClose={() => setDialog({ kind: "none" })}
        optionLabel={selectedOption.label}
        submitting={submitting}
        error={dialogError}
        onSubmit={(message) =>
          runAction(
            { type: "ask_other", quote_id: selectedOption.quote_id, message },
            {
              onSuccess: () => {
                setDialog({ kind: "none" });
                setNotice(`Sent — ${loFirstName} will be in touch.`);
              },
            },
          )
        }
      />
    </section>
  );
}
