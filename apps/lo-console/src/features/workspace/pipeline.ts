// Mirrors backend/app/workflows/constants.py's `PipelineStage` /
// `is_pipeline_stage_terminal` (CQ-016 plan.md decision #2): the six
// running-stage names an activity writes to `applications.
// last_pipeline_stage`, plus the two terminal values it's overwritten with
// once the chain stops (`needs_attention`) or finishes (`priced`). Kept in
// sync by hand -- there is no shared codegen between the two languages for
// this small a vocabulary.
const TERMINAL_STAGE_VALUES: ReadonlySet<string> = new Set(["needs_attention", "priced"]);

export function isPipelineStageTerminal(stage: string | null): boolean {
  return stage === null || TERMINAL_STAGE_VALUES.has(stage);
}

const STAGE_LABELS: Record<string, string> = {
  importing: "Importing",
  verifying: "Verifying",
  enriching: "Enriching",
  validating: "Validating",
  pricing: "Pricing",
  drafting_quotes: "Drafting quotes",
};

export function pipelineStageLabel(stage: string): string {
  return STAGE_LABELS[stage] ?? stage;
}
