import { Button } from "@cq/ui";
import type { ReportOptionData, ReportViewModelData } from "@cq/ui";

export interface ReportActionsSlotProps {
  viewModel: ReportViewModelData;
  selectedOption: ReportOptionData;
}

/**
 * Borrower actions (system-design.md "Quote report" page order step 9):
 * "I'd like to move forward with this option" and "Ask about another
 * option". CQ-024 wires these to real endpoints; until then the buttons
 * render disabled with a "Coming soon" caption, per spec.md's explicit
 * scope note for this item. Hidden entirely once the report has expired
 * (spec.md: "the report shows a ... banner, hides the actions"). Wired
 * into `ReportPage`'s `renderActions` prop from `apps/borrower-portal/src/
 * app/report/[token]/page.tsx` (plan.md Decision D3) -- `ReportPage`
 * itself already wraps this slot's output in a `print:hidden` container,
 * so this component doesn't need its own.
 */
export function ReportActionsSlot({ viewModel, selectedOption }: ReportActionsSlotProps) {
  if (viewModel.header.expired) return null;

  return (
    <section
      aria-label="Actions"
      data-testid="actions-slot"
      data-selected-quote-id={selectedOption.quote_id}
      className="flex flex-col gap-3"
    >
      <div className="flex flex-col gap-3 sm:flex-row">
        <Button type="button" disabled>
          I&rsquo;d like to move forward with this option
        </Button>
        <Button type="button" variant="secondary" disabled>
          Ask about another option
        </Button>
      </div>
      <p className="text-xs text-neutral-500">Coming soon</p>
    </section>
  );
}
