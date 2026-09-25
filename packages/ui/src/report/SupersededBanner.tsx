export interface SupersededBannerProps {
  superseded: boolean;
}

/** Shown when a newer sent version exists for this application (CQ-022's
 * versioning). Read-only history view -- no actions here. */
export function SupersededBanner({ superseded }: SupersededBannerProps) {
  if (!superseded) return null;
  return (
    <div
      role="alert"
      className="rounded-md border border-neutral-400 bg-neutral-100 px-4 py-3 text-sm text-navy-900"
    >
      <p className="font-medium">A newer version of this report has been sent.</p>
      <p className="mt-1 text-neutral-600">
        You&rsquo;re viewing an older version. Open your most recent email from your loan officer
        for current numbers.
      </p>
    </div>
  );
}
