import { APPLICATION_STATUS_TONE } from "../../types";
import type { ApplicationStatus, StatusTone } from "../../types";
import { cx } from "../../utils/cx";

export interface StatusPillProps {
  status: ApplicationStatus;
  size?: "sm" | "md";
}

const TONE_CLASSES: Record<StatusTone, string> = {
  neutral: "bg-neutral-100 text-neutral-600",
  info: "bg-status-info/10 text-status-info",
  danger: "bg-status-danger/10 text-status-danger",
  success: "bg-status-success/10 text-status-success",
  warning: "bg-status-warning/10 text-status-warning",
};

const SIZE_CLASSES: Record<NonNullable<StatusPillProps["size"]>, string> = {
  sm: "text-xs px-2 py-0.5",
  md: "text-sm px-2.5 py-1",
};

const STATUS_LABEL: Record<ApplicationStatus, string> = {
  intake: "Intake",
  verifying: "Verifying",
  needs_attention: "Needs attention",
  ready_to_price: "Ready to price",
  priced: "Priced",
  sent: "Sent",
  viewed: "Viewed",
  option_selected: "Option selected",
  inquiry: "Inquiry",
  stale: "Stale",
  withdrawn: "Withdrawn",
  closed: "Closed",
};

export function StatusPill({ status, size = "md" }: StatusPillProps) {
  const tone = APPLICATION_STATUS_TONE[status];
  return (
    <span
      data-status={status}
      data-tone={tone}
      className={cx(
        "inline-flex items-center rounded-full font-medium",
        TONE_CLASSES[tone],
        SIZE_CLASSES[size],
      )}
    >
      {STATUS_LABEL[status]}
    </span>
  );
}
