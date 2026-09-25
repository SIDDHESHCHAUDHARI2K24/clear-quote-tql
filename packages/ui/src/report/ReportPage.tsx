"use client";

import { useState } from "react";
import type { ReactNode } from "react";

import { BreakdownTable } from "./BreakdownTable";
import { CashflowTable } from "./CashflowTable";
import { Collapsible } from "./Collapsible";
import { ComparisonTable } from "./ComparisonTable";
import { CostSegTable } from "./CostSegTable";
import { Disclosures } from "./Disclosures";
import { ExpiredBanner } from "./ExpiredBanner";
import { ExplainerCards } from "./ExplainerCards";
import { HeroNumbers } from "./HeroNumbers";
import { OptionSwitcher } from "./OptionSwitcher";
import { RecommendationCard } from "./RecommendationCard";
import { ReportHeader } from "./ReportHeader";
import { SupersededBanner } from "./SupersededBanner";
import type { ReportOptionData, ReportViewModelData } from "./types";

export interface ReportPageProps {
  viewModel: ReportViewModelData;
  // A link to the newest version's report page, when `viewModel.header.
  // superseded` is true (CQ-022 spec.md). Passed straight through to
  // `SupersededBanner`.
  newestReportHref?: string;
  // Property matches (spec.md page order step 8), rendered between the
  // breakdown collapsible and disclosures. CQ-022 (borrower report) passes
  // its own `ReportMatchesSlot`; omitted (as today) when the caller has no
  // slot of its own (CQ-019's LO preview, CQ-021's gallery).
  renderMatches?: (viewModel: ReportViewModelData) => ReactNode;
  // Borrower actions (spec.md page order step 9), rendered just before
  // disclosures. CQ-022 passes its own `ReportActionsSlot`; receives the
  // currently-selected option since actions act on it.
  renderActions?: (viewModel: ReportViewModelData, selected: ReportOptionData) => ReactNode;
  // The initially-selected option's `quote_id` (defaults to `viewModel.
  // options[0]` -- the recommended option, per builder.py's ordering --
  // when omitted or unrecognized). CQ-022 passes the `?option=` query
  // param so a shared link or reload keeps the selection (spec.md AC3).
  initialSelectedId?: string;
  // Fires whenever the selected option changes (a switcher click), so a
  // caller can sync it into the URL (`?option=`). Omitted by callers that
  // don't need that (CQ-019's LO preview, CQ-021's gallery).
  onSelectionChange?: (quoteId: string) => void;
}

/**
 * Composes every report component into the full borrower-report layout, in
 * the order system-design.md's "Quote report (Tier A)" pins. Both apps'
 * `/gallery/report` pages render this for each fixture; CQ-019's LO preview
 * and CQ-022's borrower report page render it too, so the LO preview and
 * the borrower page can never structurally diverge (spec.md's whole point
 * for this item). `renderMatches`/`renderActions` are the two slots CQ-022
 * plugs into (plan.md Decision D3) -- everything else about page order
 * lives here, once, so CQ-023/CQ-024 never edit this file.
 */
export function ReportPage({
  viewModel,
  newestReportHref,
  renderMatches,
  renderActions,
  initialSelectedId,
  onSelectionChange,
}: ReportPageProps) {
  const hasInitialOption =
    initialSelectedId != null && viewModel.options.some((o) => o.quote_id === initialSelectedId);
  const [selectedId, setSelectedId] = useState(
    hasInitialOption ? (initialSelectedId as string) : (viewModel.options[0]?.quote_id ?? ""),
  );
  const selected = viewModel.options.find((o) => o.quote_id === selectedId) ?? viewModel.options[0];

  if (!selected) return null;

  function handleSelectionChange(quoteId: string) {
    setSelectedId(quoteId);
    onSelectionChange?.(quoteId);
  }

  return (
    <div className="flex flex-col gap-6">
      <ReportHeader header={viewModel.header} />
      <ExpiredBanner expired={viewModel.header.expired} />
      <SupersededBanner
        superseded={viewModel.header.superseded}
        newestReportHref={newestReportHref}
      />

      {viewModel.options.length > 1 && (
        <div className="print:hidden">
          <OptionSwitcher
            options={viewModel.options}
            selectedId={selected.quote_id}
            onChange={handleSelectionChange}
          />
        </div>
      )}

      <HeroNumbers option={selected} strategy={viewModel.strategy} />

      <RecommendationCard
        recommendation={viewModel.recommendation}
        viewingAlternative={!selected.recommended}
      />

      <ExplainerCards option={selected} strategy={viewModel.strategy} />

      {viewModel.options.length > 1 && (
        <Collapsible label={`See all ${viewModel.options.length} options we priced`}>
          <ComparisonTable options={viewModel.options} strategy={viewModel.strategy} />
        </Collapsible>
      )}

      <Collapsible label="See the full breakdown">
        <div className="flex flex-col gap-6">
          <BreakdownTable breakdown={selected.breakdown} />
          {selected.cashflow && <CashflowTable cashflow={selected.cashflow} />}
          {selected.cost_seg && <CostSegTable costSeg={selected.cost_seg} />}
        </div>
      </Collapsible>

      {renderMatches?.(viewModel)}

      {renderActions && <div className="print:hidden">{renderActions(viewModel, selected)}</div>}

      <Disclosures disclosures={viewModel.disclosures} />
    </div>
  );
}
