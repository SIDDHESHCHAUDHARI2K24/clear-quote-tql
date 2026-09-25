"use client";

import { EmptyState } from "@cq/ui";

import { formatDate } from "../../applications";
import type { ClientSentVersion } from "../types";

export interface SentVersionsTableProps {
  versions: ClientSentVersion[];
}

const STATUS_LABEL: Record<ClientSentVersion["status"], string> = {
  sent: "Sent",
  viewed: "Viewed",
  expired: "Expired",
  superseded: "Superseded",
  option_selected: "Option selected",
  move_forward: "Move forward",
  ask_other: "Asked about other options",
  ask_updated: "Asked for updated numbers",
  inquiry: "Inquiry",
};

const STATUS_CLASSES: Record<ClientSentVersion["status"], string> = {
  sent: "bg-status-info/10 text-status-info",
  viewed: "bg-status-info/10 text-status-info",
  expired: "bg-neutral-100 text-neutral-600",
  superseded: "bg-neutral-100 text-neutral-600",
  option_selected: "bg-status-success/10 text-status-success",
  move_forward: "bg-status-success/10 text-status-success",
  ask_other: "bg-status-warning/10 text-status-warning",
  ask_updated: "bg-status-warning/10 text-status-warning",
  inquiry: "bg-status-warning/10 text-status-warning",
};

/** spec.md CQ-026 "Backend"/"Frontend": one row per sent
 * `quote_package_versions` row across every application the client has --
 * sent date, recommended option, status, and a report link for the LO's
 * own preview (plan.md Decision 11). */
export function SentVersionsTable({ versions }: SentVersionsTableProps) {
  if (versions.length === 0) {
    return <EmptyState title="No quotes sent yet" body="Nothing has been sent to this client." />;
  }

  return (
    <table className="w-full border-collapse text-sm">
      <thead>
        <tr className="border-b border-neutral-200 text-left text-neutral-600">
          <th scope="col" className="px-3 py-2 font-medium">
            Sent
          </th>
          <th scope="col" className="px-3 py-2 font-medium">
            Recommended option
          </th>
          <th scope="col" className="px-3 py-2 font-medium">
            Status
          </th>
          <th scope="col" className="px-3 py-2 font-medium">
            Report
          </th>
        </tr>
      </thead>
      <tbody>
        {versions.map((version) => (
          <tr key={version.id} className="border-b border-neutral-100">
            <td className="px-3 py-3 text-navy-900">{formatDate(version.sent_at)}</td>
            <td className="px-3 py-3 text-navy-900">{version.recommended_option_label ?? "—"}</td>
            <td className="px-3 py-3">
              <span
                className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${STATUS_CLASSES[version.status]}`}
              >
                {STATUS_LABEL[version.status]}
              </span>
            </td>
            <td className="px-3 py-3">
              <a
                href={version.report_link}
                target="_blank"
                rel="noreferrer"
                className="text-navy-700 underline hover:text-navy-900"
              >
                Preview
              </a>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
