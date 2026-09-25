import { cx } from "../utils/cx";
import { formatMoney, formatMoneyPrecise, formatPercent, isNegative } from "./format";
import type { ReportMatchData } from "./types";

export interface MatchCardProps {
  match: ReportMatchData;
  /** 1-based position in the list -- renders "Match {index}" per the
   * reference screen (docs/design/reference/11-property-matches.png). */
  index: number;
}

const DEAL_GRADE_LABEL: Record<string, string> = {
  great_buy: "Great buy",
  good_buy: "Good buy",
};

interface Row {
  label: string;
  value: string;
  emphasis?: boolean;
  tone?: "danger";
}

function StatRows({ rows }: { rows: Row[] }) {
  return (
    <dl className="divide-y divide-neutral-100 text-sm">
      {rows.map((row) => (
        <div
          key={row.label}
          className={cx(
            "flex items-center justify-between gap-2 px-4 py-2",
            row.emphasis && "bg-sage-50 font-medium",
          )}
        >
          <dt className="text-neutral-600">{row.label}</dt>
          <dd className={cx("num", row.tone === "danger" ? "text-status-danger" : "text-navy-900")}>
            {row.value}
          </dd>
        </div>
      ))}
    </dl>
  );
}

/**
 * One property-match card (spec.md, packages/ui/src/report). Primary
 * matches omit rent, cashflow, cap rate and tax savings -- `match.rent_label`
 * is `null` exactly when that's the case (builder.py's `_build_match`), so
 * this component branches on that one field rather than a separate
 * "is investment" prop.
 */
export function MatchCard({ match, index }: MatchCardProps) {
  const dealGradeLabel = DEAL_GRADE_LABEL[match.deal_grade_badge] ?? match.deal_grade_badge;
  const isInvestment = match.rent_label != null;

  const rows: Row[] = [
    { label: "Total monthly payment", value: formatMoneyPrecise(match.total_monthly_payment) },
  ];
  if (isInvestment && match.rent_estimate != null) {
    rows.push({
      label: match.rent_label as string,
      value: formatMoneyPrecise(match.rent_estimate),
    });
  }
  if (isInvestment && match.monthly_cashflow != null) {
    rows.push({
      label: "Monthly cashflow",
      value: formatMoneyPrecise(match.monthly_cashflow),
      emphasis: true,
      tone: isNegative(match.monthly_cashflow) ? "danger" : undefined,
    });
  }
  rows.push({ label: "Cash to close", value: formatMoneyPrecise(match.cash_to_close) });
  if (isInvestment && match.cap_rate_pct != null) {
    rows.push({ label: "Est. cap rate", value: formatPercent(match.cap_rate_pct) });
  }
  if (isInvestment && match.year1_tax_savings != null) {
    rows.push({
      label: "Yr 1 cost seg tax savings",
      value: formatMoneyPrecise(match.year1_tax_savings),
      emphasis: true,
    });
  }

  return (
    <div
      className="flex flex-col overflow-hidden rounded-lg border border-neutral-200 bg-neutral-0 shadow-sm"
      data-testid="match-card"
    >
      <div className="relative h-36 w-full overflow-hidden bg-neutral-200">
        {/* eslint-disable-next-line @next/next/no-img-element -- packages/ui
            has no Next.js image loader; a plain img keeps this component
            framework-agnostic for both apps. */}
        <img
          src={match.property_image_url}
          alt=""
          className="h-full w-full object-cover"
          loading="lazy"
        />
        <span className="absolute left-2 top-2 rounded-full bg-navy-900/85 px-2.5 py-1 text-xs font-semibold text-neutral-0">
          Match {index}
        </span>
        <span className="absolute right-2 top-2 rounded-full bg-sage-500/90 px-2.5 py-1 text-xs font-semibold text-neutral-0">
          {dealGradeLabel}
        </span>
      </div>

      <div className="px-4 py-3">
        <p className="truncate text-sm text-neutral-600">{match.property_address}</p>
        <p className="num mt-1 text-2xl font-semibold text-navy-900">{formatMoney(match.price)}</p>
        <p className="text-xs text-neutral-500">{match.bed_bath_sqft}</p>
      </div>

      <StatRows rows={rows} />

      {match.property_tagline && (
        <p className="border-t border-neutral-100 px-4 py-2.5 text-xs text-neutral-500">
          {match.property_tagline}
        </p>
      )}
    </div>
  );
}
