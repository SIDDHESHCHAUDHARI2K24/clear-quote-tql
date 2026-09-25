"use client";

import { useWorkspace } from "./WorkspaceProvider";
import { isPipelineStageTerminal, pipelineStageLabel } from "./pipeline";

// spec.md AC7: shown while the Temporal workflow is active (`last_pipeline_
// stage` non-terminal); `WorkspaceProvider` polls every 3s while this is
// true and stops once the summary reports a terminal stage, which makes
// this banner disappear on its own.
export function PipelineBanner() {
  const { state } = useWorkspace();
  if (state.kind !== "ready") return null;

  const stage = state.summary.last_pipeline_stage;
  if (stage === null || isPipelineStageTerminal(stage)) return null;

  return (
    <div
      role="status"
      className="mx-6 mb-3 rounded-md bg-status-info/10 px-3 py-2 text-sm font-medium text-status-info"
    >
      Pipeline running: {pipelineStageLabel(stage)}
    </div>
  );
}
