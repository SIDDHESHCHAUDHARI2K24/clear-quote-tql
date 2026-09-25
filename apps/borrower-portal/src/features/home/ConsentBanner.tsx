import Link from "next/link";

export interface ConsentBannerProps {
  /** The pending consent's id (CQ-033's `/tasks/credit-check/[id]` stub). */
  consentId: string;
}

/** Task banner at the top of Home when any application has a pending
 * hard-pull consent request (spec.md Home: "Your loan officer needs your
 * permission for a credit check"). Links to CQ-033's stub page. */
export function ConsentBanner({ consentId }: ConsentBannerProps) {
  return (
    <div
      role="status"
      className="flex flex-wrap items-center justify-between gap-2 rounded-md border border-navy-200 bg-navy-50 px-4 py-3"
    >
      <p className="text-sm text-navy-900">
        Your loan officer needs your permission for a credit check.
      </p>
      <Link
        href={`/tasks/credit-check/${consentId}`}
        className="text-sm font-semibold text-navy-900 underline hover:text-navy-700"
      >
        Review and authorize
      </Link>
    </div>
  );
}
