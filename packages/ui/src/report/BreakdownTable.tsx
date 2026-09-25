import { formatMoneyPrecise } from "./format";
import type { BreakdownData } from "./types";

export interface BreakdownTableProps {
  breakdown: BreakdownData;
}

/** Payment and cash-to-close lines for the selected option (spec.md). */
export function BreakdownTable({ breakdown }: BreakdownTableProps) {
  return (
    <div className="grid gap-6 sm:grid-cols-2">
      <div>
        <h3 className="text-sm font-semibold text-navy-900">Monthly payment</h3>
        <dl className="mt-2 space-y-1.5 text-sm">
          {breakdown.payment_lines.map((line) => (
            <div key={line.label} className="flex justify-between">
              <dt className="text-neutral-600">{line.label}</dt>
              <dd className="num text-navy-900">{formatMoneyPrecise(line.amount)}</dd>
            </div>
          ))}
          <div className="flex justify-between border-t border-neutral-200 pt-1.5 font-medium">
            <dt className="text-navy-900">Total monthly payment</dt>
            <dd className="num text-navy-900">{formatMoneyPrecise(breakdown.payment_total)}</dd>
          </div>
        </dl>
      </div>
      <div>
        <h3 className="text-sm font-semibold text-navy-900">Cash to close</h3>
        <dl className="mt-2 space-y-1.5 text-sm">
          {breakdown.cash_to_close_lines.map((line) => (
            <div key={line.label} className="flex justify-between">
              <dt className="text-neutral-600">{line.label}</dt>
              <dd className="num text-navy-900">{formatMoneyPrecise(line.amount)}</dd>
            </div>
          ))}
          <div className="flex justify-between border-t border-neutral-200 pt-1.5 font-medium">
            <dt className="text-navy-900">Total cash to close</dt>
            <dd className="num text-navy-900">
              {formatMoneyPrecise(breakdown.cash_to_close_total)}
            </dd>
          </div>
        </dl>
      </div>
    </div>
  );
}
