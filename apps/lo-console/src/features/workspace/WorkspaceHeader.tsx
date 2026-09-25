"use client";

import type { ReactNode } from "react";

import { StatusPill } from "@cq/ui";

import type { ApplicationSummary } from "./api";
import { formatMoney, formatPercent, formatPpp, formatRate } from "./format";
import { PipelineBanner } from "./PipelineBanner";
import { StatusActionsMenu } from "./StatusActionsMenu";
import { TabRail } from "./TabRail";
import { useWorkspace } from "./WorkspaceProvider";

function strategyLabel(summary: ApplicationSummary): string {
  if (summary.occupancy === "primary") return "Primary";
  if (summary.strategy === "ltr") return "LTR";
  if (summary.strategy === "str") return "STR";
  return "—";
}

function locationLabel(location: ApplicationSummary["location"]): string {
  if (!location) return "—";
  const cityState = [location.city, location.state].filter(Boolean).join(", ");
  return cityState || location.zip || "—";
}

function HeaderNumber({
  label,
  value,
  muted,
  title,
}: {
  label: string;
  value: ReactNode;
  muted?: boolean;
  title?: string;
}) {
  return (
    <div title={title}>
      <dt className="text-xs font-medium uppercase tracking-wide text-neutral-500">{label}</dt>
      <dd
        className={`tabular-nums font-medium ${muted ? "text-neutral-400" : "text-navy-900"}`}
      >
        {value}
      </dd>
    </div>
  );
}

// spec.md "Sticky header": client name, status pill and the header numbers
// in order -- purchasing power, down payment (% and $), PPP, note rate,
// strategy, program, location. PPP is hidden for primary loans (AC2); the
// note rate shows "—" muted with a tooltip until a quote is recommended
// (AC3).
export function WorkspaceHeader() {
  const { applicationId, state } = useWorkspace();
  if (state.kind !== "ready") return null;
  const { summary } = state;
  const isPrimary = summary.occupancy === "primary";

  return (
    <div className="sticky top-0 z-40 border-b border-neutral-200 bg-neutral-0">
      <div className="flex flex-wrap items-center justify-between gap-3 px-6 py-4">
        <div className="flex items-center gap-3">
          <h1 className="text-lg font-semibold text-navy-900">{summary.client_name}</h1>
          <StatusPill status={summary.status} />
        </div>
        <StatusActionsMenu />
      </div>
      <dl className="flex flex-wrap gap-x-8 gap-y-3 px-6 pb-4 text-sm">
        <HeaderNumber label="Purchasing power" value={formatMoney(summary.purchasing_power)} />
        <HeaderNumber
          label="Down payment"
          value={`${formatPercent(summary.down_payment_pct)} · ${formatMoney(summary.down_payment_amount)}`}
        />
        {!isPrimary && <HeaderNumber label="PPP" value={formatPpp(summary.ppp_years)} />}
        <HeaderNumber
          label="Note rate"
          value={formatRate(summary.note_rate)}
          muted={summary.note_rate === null}
          title={summary.note_rate === null ? "Set after pricing" : undefined}
        />
        <HeaderNumber label="Strategy" value={strategyLabel(summary)} />
        <HeaderNumber label="Program" value={summary.program ?? "—"} />
        <HeaderNumber label="Location" value={locationLabel(summary.location)} />
      </dl>
      <PipelineBanner />
      <div className="px-6">
        <TabRail applicationId={applicationId} tabs={summary.tabs} />
      </div>
    </div>
  );
}
