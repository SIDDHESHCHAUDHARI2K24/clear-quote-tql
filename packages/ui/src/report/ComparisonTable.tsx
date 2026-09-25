import { cx } from "../utils/cx";
import { formatMoney, formatPercent } from "./format";
import type { ReportOptionData, ReportStrategyData } from "./types";

export interface ComparisonTableProps {
  options: ReportOptionData[];
  strategy: ReportStrategyData;
}

interface Row {
  label: string;
  render: (option: ReportOptionData) => string;
  investmentOnly?: boolean;
}

const ROWS: Row[] = [
  { label: "Rate", render: (o) => formatPercent(o.rate) },
  { label: "Points", render: (o) => formatPercent(o.points_pct) },
  { label: "Down payment", render: (o) => formatPercent(o.down_payment_pct) },
  { label: "Prepayment penalty", render: (o) => o.prepay_label, investmentOnly: true },
  { label: "Monthly payment", render: (o) => formatMoney(o.hero.monthly_payment) },
  { label: "Cash to close", render: (o) => formatMoney(o.hero.cash_to_close) },
  {
    label: "Monthly cashflow",
    render: (o) => (o.hero.monthly_cashflow ? formatMoney(o.hero.monthly_cashflow) : "—"),
    investmentOnly: true,
  },
  {
    label: "DSCR",
    render: (o) => (o.cashflow ? o.cashflow.dscr : "—"),
    investmentOnly: true,
  },
];

/**
 * All options side by side (spec.md); rows follow the reference
 * pricing-options screen. Strategy-gated rows are hidden for primary --
 * `ROWS.investmentOnly` never renders when `strategy === "primary"`.
 */
export function ComparisonTable({ options, strategy }: ComparisonTableProps) {
  const rows = ROWS.filter((row) => !row.investmentOnly || strategy !== "primary");

  return (
    <table className="w-full border-collapse text-sm print:break-inside-avoid">
      <thead>
        <tr className="border-b border-neutral-200 text-left text-neutral-600">
          <th scope="col" className="px-3 py-2 font-medium">
            &nbsp;
          </th>
          {options.map((option) => (
            <th
              key={option.quote_id}
              scope="col"
              className={cx(
                "px-3 py-2 text-right font-medium",
                option.recommended && "bg-sage-50 text-sage-900",
              )}
            >
              {option.label}
              {option.recommended && <span className="ml-1 text-sage-500">★</span>}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {rows.map((row) => (
          <tr key={row.label} className="border-b border-neutral-100">
            <th scope="row" className="px-3 py-2 text-left font-medium text-neutral-600">
              {row.label}
            </th>
            {options.map((option) => (
              <td
                key={option.quote_id}
                className={cx(
                  "num px-3 py-2 text-right text-navy-900",
                  option.recommended && "bg-sage-50",
                )}
              >
                {row.render(option)}
              </td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );
}
