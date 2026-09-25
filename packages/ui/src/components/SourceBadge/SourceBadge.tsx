import type { SourceBadgeSource } from "../../types";
import { cx } from "../../utils/cx";

// Mirrors CQ-007's FieldSource enum exactly (12 values, owner: CQ-007).
export interface SourceBadgeProps {
  source: SourceBadgeSource;
  onRevert?: () => void; // rendered only when source === 'lo_override'
}

const SOURCE_LABEL: Record<SourceBadgeSource, string> = {
  encompass: "Encompass",
  rentcast: "RentCast",
  airdna: "AirDNA",
  smartasset: "SmartAsset",
  steadily: "Steadily",
  optimal_blue: "Optimal Blue",
  credit_bureau: "Credit bureau",
  property_search: "Property search",
  lo_entry: "LO entry",
  formula: "Formula",
  default: "Default",
  lo_override: "LO override",
};

export function SourceBadge({ source, onRevert }: SourceBadgeProps) {
  return (
    <span
      data-source={source}
      className={cx(
        "inline-flex items-center gap-1 rounded-full bg-navy-50 px-2 py-0.5 text-xs font-medium text-navy-700",
      )}
    >
      {SOURCE_LABEL[source]}
      {source === "lo_override" && onRevert && (
        <button
          type="button"
          aria-label="Revert to source"
          onClick={onRevert}
          className="ml-1 text-navy-500 underline hover:text-navy-700"
        >
          revert
        </button>
      )}
    </span>
  );
}
