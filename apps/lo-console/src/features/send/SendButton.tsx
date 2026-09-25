"use client";

import { useState } from "react";

import { Button, Overlay } from "@cq/ui";

import type { Readiness, SendPackage } from "./api";

export const SEND_STUB_MESSAGE = "Sending arrives in CQ-020";

export interface SendButtonProps {
  pkg: SendPackage;
  readiness: Readiness | null;
}

/** Disabled with the first blocker as its tooltip until the package is
 * ready; then a confirm dialog with the recipient and attachments. The
 * dialog's action is a stub until CQ-020 adds the send endpoint. */
export function SendButton({ pkg, readiness }: SendButtonProps) {
  const [open, setOpen] = useState(false);
  const [stubbed, setStubbed] = useState(false);
  const ready = readiness?.ready === true;
  const tooltip = readiness === null ? "Checking readiness…" : readiness.blockers[0]?.message;

  return (
    <>
      <span title={ready ? undefined : tooltip} data-testid="send-button-wrapper">
        <Button disabled={!ready} onClick={() => setOpen(true)}>
          Send to borrower
        </Button>
      </span>
      {!ready && tooltip && (
        <p className="text-xs text-neutral-600" data-testid="send-blocked-reason">
          {tooltip}
        </p>
      )}
      <Overlay
        isOpen={open}
        onClose={() => {
          setOpen(false);
          setStubbed(false);
        }}
        title="Send quotes to the borrower?"
        size="sm"
        footer={
          <div className="flex justify-end gap-2">
            <Button variant="ghost" onClick={() => setOpen(false)}>
              Cancel
            </Button>
            <Button onClick={() => setStubbed(true)}>Send</Button>
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
        {stubbed && (
          <p role="status" className="mt-3 text-sm font-medium text-navy-700">
            {SEND_STUB_MESSAGE}
          </p>
        )}
      </Overlay>
    </>
  );
}
