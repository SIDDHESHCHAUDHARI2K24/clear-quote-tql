import type { BuilderStrategy, ScenarioGroup } from "./api";
import { QuoteCard } from "./QuoteCard";

export const MAX_COMPARE = 3;

export interface QuoteGroupsProps {
  groups: ScenarioGroup[];
  strategy: BuilderStrategy | null;
  busy: boolean;
  compareIds: string[];
  onRecommend: (quoteId: string) => void;
  onEdit: (group: ScenarioGroup) => void;
  onDelete: (quoteId: string) => void;
  onToggleCompare: (quoteId: string) => void;
}

/** The pipeline's default scenario groups (and any the LO added), each a
 * heading built server-side ("At DSCR 1.00", "At 5% down", ...) over its
 * quote cards. */
export function QuoteGroups({
  groups,
  strategy,
  busy,
  compareIds,
  onRecommend,
  onEdit,
  onDelete,
  onToggleCompare,
}: QuoteGroupsProps) {
  if (groups.length === 0) {
    return (
      <p className="rounded-lg border border-dashed border-neutral-200 p-6 text-center text-sm text-neutral-600">
        No quotes yet. Add a scenario to price this application.
      </p>
    );
  }
  const compareFull = compareIds.length >= MAX_COMPARE;
  const compareSet = new Set(compareIds);
  return (
    <div className="flex flex-col gap-6">
      {groups.map((group) => (
        <section key={group.id} data-testid="quote-group" className="flex flex-col gap-3">
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <h3 className="text-md font-semibold text-navy-900">{group.label}</h3>
            <button
              type="button"
              onClick={() => onEdit(group)}
              disabled={busy}
              className="text-sm font-medium text-navy-700 underline"
            >
              Edit scenario
            </button>
          </div>
          {group.note && <p className="text-sm text-neutral-600">{group.note}</p>}
          {group.quotes.length === 0 ? (
            <p className="text-sm text-neutral-600">No quotes in this scenario.</p>
          ) : (
            <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
              {group.quotes.map((quote) => (
                <QuoteCard
                  key={quote.id}
                  quote={quote}
                  strategy={strategy}
                  busy={busy}
                  selected={compareSet.has(quote.id)}
                  selectDisabled={compareFull}
                  onRecommend={onRecommend}
                  onEdit={() => onEdit(group)}
                  onDelete={onDelete}
                  onToggleCompare={onToggleCompare}
                />
              ))}
            </div>
          )}
        </section>
      ))}
    </div>
  );
}
