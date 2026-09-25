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

// PR review round 1 (minor): `import_application` has no `verify`/`enrich`-
// style "blocked" status transition (spec.md: a failed import is a setup
// error, not a demo path), so a failed import never advances `status` past
// `intake` -- but `workflows/activities.py` does still write the terminal
// `needs_attention` stage marker on failure (CQ-016's own code-review fix),
// so this exact combination (`status === "intake"` with a *terminal*
// `last_pipeline_stage`) can only happen via that one path. Used to show an
// "Import failed" banner instead of silently showing nothing once the
// (correctly stopped) polling banner disappears.
export function isImportFailure(status: string, stage: string | null): boolean {
  return status === "intake" && stage !== null && isPipelineStageTerminal(stage);
}
