"use client";

import { useEffect, useState } from "react";

import { extractErrorMessage } from "@cq/ui";

import { attachmentDownloadUrl, fetchOutboxDetail } from "./api";
import type { OutboxEmailDetail as OutboxEmailDetailType } from "./api";

export interface OutboxDetailProps {
  emailId: string;
}

type LoadState =
  | { kind: "loading" }
  | { kind: "error"; message: string }
  | { kind: "ready"; detail: OutboxEmailDetailType };

/** spec.md CQ-029 "Outbox" detail view: the HTML body in a sandboxed
 * iframe (AC7: `sandbox=""`, no scripts) and attachment downloads. */
export function OutboxDetail({ emailId }: OutboxDetailProps) {
  const [state, setState] = useState<LoadState>({ kind: "loading" });

  useEffect(() => {
    let cancelled = false;
    setState({ kind: "loading" });
    fetchOutboxDetail(emailId).then(({ data, error }) => {
      if (cancelled) return;
      if (error || !data) {
        setState({
          kind: "error",
          message: extractErrorMessage(error, "Couldn't load this email. Try again."),
        });
        return;
      }
      setState({ kind: "ready", detail: data });
    });
    return () => {
      cancelled = true;
    };
  }, [emailId]);

  if (state.kind === "loading") {
    return (
      <p role="status" className="text-sm text-neutral-600">
        Loading email…
      </p>
    );
  }

  if (state.kind === "error") {
    return (
      <p role="alert" className="text-sm text-status-danger">
        {state.message}
      </p>
    );
  }

  const { detail } = state;

  return (
    <div className="flex flex-col gap-4">
      <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-sm">
        <dt className="font-medium text-neutral-600">To</dt>
        <dd>{detail.to_email}</dd>
        <dt className="font-medium text-neutral-600">Subject</dt>
        <dd>{detail.subject}</dd>
        <dt className="font-medium text-neutral-600">Application</dt>
        <dd>{detail.client_name ?? "—"}</dd>
      </dl>

      <iframe
        title={`Email: ${detail.subject}`}
        srcDoc={detail.html}
        sandbox=""
        className="h-96 w-full rounded-md border border-neutral-200 bg-neutral-0"
      />

      {detail.attachments.length > 0 && (
        <div>
          <h3 className="mb-1 text-sm font-medium text-navy-900">Attachments</h3>
          <ul className="flex flex-col gap-1">
            {detail.attachments.map((attachment) => (
              <li key={attachment.key}>
                <a
                  href={attachmentDownloadUrl(detail.id, attachment.key)}
                  className="text-sm text-navy-700 underline hover:text-navy-900"
                >
                  {attachment.filename}
                </a>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
