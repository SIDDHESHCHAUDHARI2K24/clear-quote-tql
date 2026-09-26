import type { SectionFlag } from "./api";

function cx(...classes: (string | false | undefined)[]): string {
  return classes.filter(Boolean).join(" ");
}

export interface FlagListProps {
  flags: SectionFlag[];
}

const SEVERITY_CLASSES: Record<SectionFlag["severity"], string> = {
  blocking: "border-status-danger bg-status-danger/5 text-status-danger",
  warning: "border-status-warning bg-status-warning/5 text-status-warning",
  info: "border-neutral-200 bg-neutral-50 text-neutral-600",
};

/** The tab's open flags, listed at the top (spec.md "Shared pieces"). Each
 * flagged field is also highlighted inline by `FieldRow`; this is the
 * at-a-glance summary an LO scans first. */
export function FlagList({ flags }: FlagListProps) {
  if (flags.length === 0) return null;
  return (
    <ul className="mb-4 flex flex-col gap-2" aria-label="Open flags">
      {flags.map((flag) => (
        <li
          key={flag.id}
          className={cx(
            "rounded-md border-l-4 px-3 py-2 text-sm font-medium",
            SEVERITY_CLASSES[flag.severity],
          )}
        >
          {flag.message ?? flag.rule}
        </li>
      ))}
    </ul>
  );
}
