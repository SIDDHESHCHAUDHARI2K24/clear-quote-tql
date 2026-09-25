"use client";

import { isImportFailure, isPipelineStageTerminal, pipelineStageLabel } from "./pipeline";
import { useWorkspace } from "./WorkspaceProvider";

// spec.md AC7: shown while the Temporal workflow is active (`last_pipeline_
// stage` non-terminal); `WorkspaceProvider` polls every 3s while this is
// true and stops once the summary reports a terminal stage, which makes
// this banner disappear on its own.
//
// PR review round 1 (minor): a failed import is the one path with no
// "blocked" status transition (see `pipeline.ts::isImportFailure`) -- show
// an explicit error banner for it instead of just letting the "running"
// banner silently disappear with no other visible sign anything went
// wrong.
export function PipelineBanner() {
  const { state } = useWorkspace();
  if (state.kind !== "ready") return null;

  const stage = state.summary.last_pipeline_stage;

  if (isImportFailure(state.summary.status, stage)) {
    return (
      <div
        role="alert"
        className="mx-6 mb-3 rounded-md bg-status-danger/10 px-3 py-2 text-sm font-medium text-status-danger"
      >
        Import failed. Contact support.
      </div>
    );
  }

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
