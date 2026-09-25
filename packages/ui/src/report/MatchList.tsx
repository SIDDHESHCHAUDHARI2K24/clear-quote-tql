import { MatchCard } from "./MatchCard";
import type { ReportMatchData } from "./types";

export interface MatchListProps {
  matches: ReportMatchData[];
}

/**
 * "Your top 3 property matches" section (spec.md; system-design.md Quote
 * report step 8). One column at 375px, three columns at 1120px+ (AC8) --
 * `lg:` (Tailwind's 1024px breakpoint) is the first breakpoint at or below
 * 1120px. Hidden entirely with no matches -- CQ-022's `ReportMatchesSlot`
 * already guards on `matches.length === 0` before rendering this, but this
 * component guards too so any other caller (the gallery, CQ-019's LO
 * preview) gets the same "no matches -> nothing" behavior for free.
 */
export function MatchList({ matches }: MatchListProps) {
  if (matches.length === 0) return null;

  return (
    <section data-testid="match-list" className="print:break-inside-avoid">
      <h2 className="text-lg font-semibold text-navy-900">Your top 3 property matches</h2>
      <p className="mt-1 text-sm text-neutral-600">
        Selected for your budget and markets, each run through the same numbers
      </p>
      <div className="mt-4 grid grid-cols-1 gap-4 lg:grid-cols-3">
        {matches.map((match, i) => (
          <MatchCard key={match.matched_property_id} match={match} index={i + 1} />
        ))}
      </div>
    </section>
  );
}
