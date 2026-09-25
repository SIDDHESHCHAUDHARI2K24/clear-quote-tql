import type { PortalStage } from "./api";

function cx(...parts: Array<string | false | null | undefined>): string {
  return parts.filter(Boolean).join(" ");
}

const STEPS = ["Applied", "In review", "Pre-approved", "Option selected"] as const;

/** Only the four stages the 4-step bar (spec.md Home) covers; `closed` and
 * `draft` cards render without a progress bar (`ApplicationCard`). */
const STEP_INDEX: Partial<Record<PortalStage, number>> = {
  applied: 0,
  in_review: 1,
  preapproved: 2,
  option_selected: 3,
};

export interface ProgressBarProps {
  stage: PortalStage;
}

/** The 4-step "Applied → In review → Pre-approved → Option selected" bar
 * (spec.md Home). Renders nothing for a stage the bar doesn't cover
 * (`closed`, `draft`) -- `ApplicationCard` only mounts this for the four
 * stages above. */
export function ProgressBar({ stage }: ProgressBarProps) {
  const currentIndex = STEP_INDEX[stage];
  if (currentIndex === undefined) return null;

  return (
    <ol aria-label="Application progress" className="flex w-full items-center gap-1">
      {STEPS.map((label, index) => {
        const isComplete = index < currentIndex;
        const isCurrent = index === currentIndex;
        return (
          <li key={label} className="flex flex-1 flex-col items-center gap-1 text-center">
            <span
              aria-hidden="true"
              className={cx(
                "h-1.5 w-full rounded-full",
                isComplete || isCurrent ? "bg-navy-500" : "bg-neutral-200",
              )}
            />
            <span
              aria-current={isCurrent ? "step" : undefined}
              className={cx(
                "text-xs leading-tight",
                isCurrent
                  ? "font-semibold text-navy-900"
                  : isComplete
                    ? "text-navy-700"
                    : "text-neutral-500",
              )}
            >
              {label}
            </span>
          </li>
        );
      })}
    </ol>
  );
}
