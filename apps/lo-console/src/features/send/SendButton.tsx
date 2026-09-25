"use client";

import { useState } from "react";

import { Button, Overlay } from "@cq/ui";

import type { Readiness, SendPackage } from "./api";
import { SendProgress } from "./SendProgress";
import type { SendPhase } from "./useSendFlow";

export interface SendButtonProps {
  pkg: SendPackage;
  readiness: Readiness | null;
  phase: SendPhase;
  onSend: () => void;
  /** Clears a finished, failed or blocked send when the dialog closes. */
  onReset: () => void;
}

/** Disabled with the first blocker as its tooltip until the package is
 * ready; then a confirm dialog with the recipient and attachments. Send
 * starts the workflow and the dialog follows its progress. */
export function SendButton({ pkg, readiness, phase, onSend, onReset }: SendButtonProps) {
  const [open, setOpen] = useState(false);
  const ready = readiness?.ready === true;
  const tooltip = readiness === null ? "Checking readiness…" : readiness.blockers[0]?.message;
  const inFlight = phase.kind === "starting" || phase.kind === "running";
  const finished = phase.kind === "done";
  const alreadySent = pkg.sent_at !== null;

  const close = () => {
    setOpen(false);
    onReset();
  };

  return (
    <>
      <span title={ready ? undefined : tooltip} data-testid="send-button-wrapper">
        <Button
          disabled={!ready || inFlight}
          onClick={() => {
            // A finished send's "Done" belongs to that send, not this one.
            if (finished) onReset();
            setOpen(true);
          }}
        >
          {inFlight ? "Sending…" : alreadySent ? "Send again" : "Send to borrower"}
        </Button>
      </span>
      {!ready && tooltip && (
        <p className="text-xs text-neutral-600" data-testid="send-blocked-reason">
          {tooltip}
        </p>
      )}
      {!open && (inFlight || phase.kind === "failed") && <SendProgress phase={phase} compact />}
      <Overlay
        isOpen={open}
        onClose={close}
        title={finished ? "Sent" : "Send quotes to the borrower?"}
        size="sm"
        footer={
          <div className="flex justify-end gap-2">
            {finished || phase.kind === "blocked" ? (
              <Button onClick={close}>Close</Button>
            ) : (
              <>
                <Button variant="ghost" onClick={close}>
                  {inFlight ? "Hide" : "Cancel"}
                </Button>
                <Button disabled={inFlight} onClick={onSend}>
                  {phase.kind === "failed" ? "Try again" : "Send"}
                </Button>
              </>
            )}
          </div>
        }
      >
        <dl className="flex flex-col gap-2 text-sm text-navy-900">
          <div>
            <dt className="text-neutral-600">Recipient</dt>
            <dd data-testid="send-recipient">{pkg.recipient_email ?? "—"}</dd>
          </div>
          <div>
            <dt className="text-neutral-600">Attachments</dt>
            {pkg.attachments.map((name) => (
              <dd key={name}>{name}</dd>
            ))}
          </div>
          <div>
            <dt className="text-neutral-600">Quotes</dt>
            <dd>{pkg.quote_ids.length} option(s), with a link to the full report</dd>
          </div>
        </dl>
        <SendProgress phase={phase} />
      </Overlay>
    </>
  );
}
