import type { SendPhase } from "./useSendFlow";

const STEPS = ["Rendering letter", "Emailing", "Done"] as const;

/** Which of STEPS is current: queued/rendering → 0, emailing → 1, done → 2. */
function currentStep(phase: SendPhase): number {
  if (phase.kind === "done") return 2;
  if (phase.kind === "running" && phase.step === "emailing") return 1;
  return 0;
}

export interface SendProgressProps {
  phase: SendPhase;
  /** One line under the Send button instead of the dialog's step list. */
  compact?: boolean;
}

/** Rendering letter → Emailing → Done, plus a not-ready or failed send's
 * reason. Nothing for an idle send. */
export function SendProgress({ phase, compact = false }: SendProgressProps) {
  if (phase.kind === "idle") return null;

  if (phase.kind === "blocked") {
    return (
      <div role="alert" className="mt-3 flex flex-col gap-1 text-sm" data-testid="send-blocked">
        <p className="font-medium text-status-danger">{phase.message}</p>
        <ul className="list-disc pl-5 text-navy-900">
          {phase.blockers.map((blocker) => (
            <li key={`${blocker.code}:${blocker.message}`}>{blocker.message}</li>
          ))}
        </ul>
      </div>
    );
  }

  if (phase.kind === "failed") {
    return (
      <p role="alert" className="mt-3 text-sm text-status-danger" data-testid="send-failed">
        Send failed: {phase.message}
      </p>
    );
  }

  const current = currentStep(phase);
  if (compact) {
    return (
      <p role="status" className="text-xs text-neutral-600" data-testid="send-progress-inline">
        {STEPS[current]}…
      </p>
    );
  }
  return (
    <ol
      className="mt-4 flex flex-col gap-1 text-sm"
      aria-label="Send progress"
      data-testid="send-progress"
    >
      {STEPS.map((label, index) => {
        const complete = index < current || phase.kind === "done";
        const active = index === current && phase.kind !== "done";
        return (
          <li
            key={label}
            aria-current={active ? "step" : undefined}
            className={`flex items-center gap-2 ${
              complete
                ? "text-status-success"
                : active
                  ? "font-medium text-navy-900"
                  : "text-neutral-600"
            }`}
          >
            <span aria-hidden="true">{complete ? "✓" : active ? "•" : "○"}</span>
            {label}
          </li>
        );
      })}
    </ol>
  );
}
