import { MatchList } from "@cq/ui";
import type { ReportViewModelData } from "@cq/ui";

export interface ReportMatchesSlotProps {
  viewModel: ReportViewModelData;
}

/**
 * Property matches (system-design.md "Quote report" page order step 8: "3
 * cards run through the same numbers"). `viewModel.matches` is `[]` for a
 * specific-address application, an application with `recommend_matches`
 * off, or one with no matches computed yet (`app.features.matches.service
 * .compute_matches_for_package`) -- `MatchList` itself already renders
 * nothing for an empty list, so this slot just passes the data through.
 * Wired into `ReportPage`'s `renderMatches` prop from
 * `apps/borrower-portal/src/app/report/[token]/page.tsx`.
 */
export function ReportMatchesSlot({ viewModel }: ReportMatchesSlotProps) {
  return <MatchList matches={viewModel.matches} />;
}
