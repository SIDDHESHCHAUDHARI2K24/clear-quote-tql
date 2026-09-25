export interface ExpiredBannerProps {
  expired: boolean;
}

/** "These numbers have expired" banner past 21 days (system-design.md).
 * Actions are hidden and "Ask for updated numbers" is offered by CQ-024 --
 * this component only renders the banner text itself. */
export function ExpiredBanner({ expired }: ExpiredBannerProps) {
  if (!expired) return null;
  return (
    <div
      role="alert"
      className="rounded-md border border-status-warning bg-status-warning/10 px-4 py-3 text-sm text-navy-900"
    >
      <p className="font-medium">These numbers have expired.</p>
      <p className="mt-1 text-neutral-600">
        Rates move daily -- ask your loan officer for updated numbers before moving forward.
      </p>
    </div>
  );
}
