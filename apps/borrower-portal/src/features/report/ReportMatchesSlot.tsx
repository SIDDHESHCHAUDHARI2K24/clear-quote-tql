import type { ReportViewModelData } from "@cq/ui";

export interface ReportMatchesSlotProps {
  viewModel: ReportViewModelData;
}

/**
 * Property matches (system-design.md "Quote report" page order step 8: "3
 * cards run through the same numbers"). `viewModel.matches` is always `[]`
 * until CQ-023 lands its match service (CQ-021 review, plan.md Decision
 * D3) -- this slot renders nothing in that case. Wired into `ReportPage`'s
 * `renderMatches` prop from `apps/borrower-portal/src/app/report/[token]/
 * page.tsx`, so CQ-023 only ever edits this one file, never the page or
 * `ReportPage` itself.
 */
export function ReportMatchesSlot({ viewModel }: ReportMatchesSlotProps) {
  if (viewModel.matches.length === 0) return null;

  // CQ-023 fills this in with MatchCard/MatchList (packages/ui/src/report/).
  return null;
}
