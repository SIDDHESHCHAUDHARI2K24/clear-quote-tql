export interface SupersededBannerProps {
  superseded: boolean;
  // A link to the newest version's report page (CQ-022 spec.md: "shows the
  // expired banner ... SupersededBanner with a link to the newest
  // version"). Omitted when the caller has no newer token to link to (e.g.
  // CQ-021's gallery fixtures) -- the banner still renders without a link.
  newestReportHref?: string;
}

/** Shown when a newer sent version exists for this application (CQ-022's
 * versioning). Read-only history view -- no actions here. */
export function SupersededBanner({ superseded, newestReportHref }: SupersededBannerProps) {
  if (!superseded) return null;
  return (
    <div
      role="alert"
      className="rounded-md border border-neutral-400 bg-neutral-100 px-4 py-3 text-sm text-navy-900"
    >
      <p className="font-medium">A newer version of this report has been sent.</p>
      <p className="mt-1 text-neutral-600">
        You&rsquo;re viewing an older version.{" "}
        {newestReportHref ? (
          <a href={newestReportHref} className="text-navy-500 underline hover:text-navy-700">
            Open your most recent report
          </a>
        ) : (
          "Open your most recent email from your loan officer for current numbers."
        )}
      </p>
    </div>
  );
}
