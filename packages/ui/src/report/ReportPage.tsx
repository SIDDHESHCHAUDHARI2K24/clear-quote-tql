"use client";

import { useState } from "react";

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
import type { ReportViewModelData } from "./types";

export interface ReportPageProps {
  viewModel: ReportViewModelData;
}

/**
 * Composes every report component into the full borrower-report layout, in
 * the order system-design.md's "Quote report (Tier A)" pins. Both apps'
 * `/gallery/report` pages render this for each fixture; CQ-019's LO preview
 * and CQ-022's borrower report page will render it too, so the LO preview
 * and the borrower page can never structurally diverge (spec.md's whole
 * point for this item). Property matches (step 8) are CQ-023's job --
 * `viewModel.matches` is always `[]` here, so nothing renders for it yet.
 */
export function ReportPage({ viewModel }: ReportPageProps) {
  const [selectedId, setSelectedId] = useState(viewModel.options[0]?.quote_id ?? "");
  const selected = viewModel.options.find((o) => o.quote_id === selectedId) ?? viewModel.options[0];

  if (!selected) return null;

  return (
    <div className="flex flex-col gap-6">
      <ReportHeader header={viewModel.header} />
      <ExpiredBanner expired={viewModel.header.expired} />
      <SupersededBanner superseded={viewModel.header.superseded} />

      {viewModel.options.length > 1 && (
        <OptionSwitcher
          options={viewModel.options}
          selectedId={selected.quote_id}
          onChange={setSelectedId}
        />
      )}

      <HeroNumbers option={selected} strategy={viewModel.strategy} />

      <RecommendationCard recommendation={viewModel.recommendation} />

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

      <Disclosures disclosures={viewModel.disclosures} />
    </div>
  );
}
