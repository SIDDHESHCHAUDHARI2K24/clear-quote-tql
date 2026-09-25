"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";

import { Button, Card } from "@cq/ui";

import type { PortalApplicationOut } from "./api";
import { ProgressBar } from "./ProgressBar";

const NEXT_ACTION_COPY: Record<
  string,
  { label: string; href: (a: PortalApplicationOut) => string }
> = {
  view_report: {
    label: "See your numbers",
    href: (a) => `/report/${a.next_action.report_token}`,
  },
  continue_application: {
    label: "Continue your application",
    href: () => "/apply",
  },
  authorize_credit_check: {
    label: "Authorize the credit check",
    href: (a) => `/tasks/credit-check/${a.next_action.consent_id}`,
  },
};

export interface ApplicationCardProps {
  application: PortalApplicationOut;
}

/** One card per application (spec.md Home): the 4-step progress bar (for
 * the four stages it covers), the plain-language `label`, the one
 * next-action button, a secondary "View your numbers" link when a sent
 * report exists but isn't the primary action (Luis Romero, AC3), and the
 * assigned LO's contact card. Renders only `stage`/`label` text the
 * backend already produced -- no status re-derivation here. */
export function ApplicationCard({ application }: ApplicationCardProps) {
  const router = useRouter();
  const { stage, label, next_action, secondary_report_token, lo } = application;
  const actionCopy = NEXT_ACTION_COPY[next_action.type];
  const showProgressBar = stage !== "closed" && stage !== "draft";

  return (
    <Card>
      <div className="flex flex-col gap-4">
        {showProgressBar && <ProgressBar stage={stage} />}

        <p role="status" className="text-md font-medium text-navy-900">
          {label}
        </p>

        <div className="flex flex-wrap items-center gap-3">
          {actionCopy && (
            <Button onClick={() => router.push(actionCopy.href(application))}>
              {actionCopy.label}
            </Button>
          )}
          {secondary_report_token && (
            <Link
              href={`/report/${secondary_report_token}`}
              className="text-sm font-medium text-navy-700 underline hover:text-navy-900"
            >
              View your numbers
            </Link>
          )}
        </div>

        {lo && (
          <div className="rounded-md border border-neutral-200 bg-neutral-50 p-3 text-sm text-neutral-700">
            <p className="font-medium text-navy-900">{lo.name}</p>
            <p>{lo.email}</p>
            {lo.phone && <p>{lo.phone}</p>}
          </div>
        )}
      </div>
    </Card>
  );
}
