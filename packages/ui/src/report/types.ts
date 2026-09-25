// Re-exports of the generated `@cq/api-client` schema types under names that
// don't collide with this directory's own component names (e.g. the
// `HeroNumbers` component vs. the `HeroNumbers` schema type). Per CQ-021
// spec.md: "The generated TypeScript type from the api-client is the
// component props type" -- every report component takes one of these types
// (or a slice of one), never a hand-written shape, so a schema change is a
// compile error here instead of a silent drift between CQ-019 and CQ-022.
import type { components } from "@cq/api-client";

export type ReportViewModelData = components["schemas"]["ReportViewModel"];
export type ReportHeaderData = components["schemas"]["ReportHeader"];
export type ReportOptionData = components["schemas"]["ReportOption"];
export type HeroNumbersData = components["schemas"]["HeroNumbers"];
export type BreakdownData = components["schemas"]["Breakdown"];
export type BreakdownLineData = components["schemas"]["BreakdownLine"];
export type CashflowTableData = components["schemas"]["CashflowTable"];
export type CostSegTableData = components["schemas"]["CostSegTable"];
export type ReportRecommendationData = components["schemas"]["ReportRecommendation"];
export type ReportMatchData = components["schemas"]["ReportMatch"];
export type ReportDisclosuresData = components["schemas"]["ReportDisclosures"];
export type ReportLoData = components["schemas"]["ReportLo"];
export type ReportStrategyData = components["schemas"]["ReportStrategy"];
