import Link from "next/link";

import type { PricingProblem } from "./api";

const TAB_NAMES: Record<string, string> = {
  borrowers: "Borrowers",
  housing: "Housing",
  credit: "Credit",
  assets: "Assets",
  property: "Property",
  pricing: "Pricing",
};

export interface PricingProblemNoticeProps {
  applicationId: string;
  problem: PricingProblem;
}

/** spec: a pricing 422 shows "Cannot price: missing {Field}" with a link
 * to the workspace tab that owns the field. */
export function PricingProblemNotice({ applicationId, problem }: PricingProblemNoticeProps) {
  const tabName = problem.tab ? (TAB_NAMES[problem.tab] ?? problem.tab) : null;
  return (
    <div
      role="alert"
      className="flex flex-wrap items-center justify-between gap-3 rounded-md border border-status-danger bg-status-danger/10 px-4 py-3 text-sm text-navy-900"
    >
      <span>{problem.field ? `Cannot price: missing ${problem.field}` : problem.message}</span>
      {problem.tab && tabName && (
        <Link
          href={`/applications/${applicationId}/${problem.tab}`}
          className="font-medium text-navy-700 underline"
        >
          Fix on the {tabName} tab
        </Link>
      )}
    </div>
  );
}
