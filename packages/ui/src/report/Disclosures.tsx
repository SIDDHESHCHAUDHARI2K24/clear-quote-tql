import type { ReportDisclosuresData } from "./types";

export interface DisclosuresProps {
  disclosures: ReportDisclosuresData;
}

/** Footer text by strategy: core always, investment + tax only when set
 * (spec.md). Primary loans get `investment`/`tax` as `null` from the
 * builder -- never rendered here, not just hidden by CSS. */
export function Disclosures({ disclosures }: DisclosuresProps) {
  return (
    <footer className="space-y-2 border-t border-neutral-200 pt-4 text-xs text-neutral-600">
      <p>{disclosures.core}</p>
      {disclosures.investment && <p>{disclosures.investment}</p>}
      {disclosures.tax && <p>{disclosures.tax}</p>}
    </footer>
  );
}
