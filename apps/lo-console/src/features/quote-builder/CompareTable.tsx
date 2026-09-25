import { formatPercent } from "@cq/ui";

import { formatMoneyCents } from "../pricing/format";
import type { BuilderStrategy, QuoteCardData } from "./api";

export interface CompareTableProps {
  quotes: QuoteCardData[];
  strategy: BuilderStrategy | null;
}

interface Row {
  label: string;
  render: (quote: QuoteCardData) => string;
  investmentOnly?: boolean;
}

// The same rows, in the same order, as the borrower's comparison table
// (`packages/ui/src/report/ComparisonTable.tsx`, plan.md Decision 12).
const ROWS: Row[] = [
  { label: "Rate", render: (q) => formatPercent(q.rate_pct) },
  { label: "Points", render: (q) => formatPercent(q.points_pct) },
  { label: "Down payment", render: (q) => formatPercent(q.down_payment_pct) },
  { label: "Prepayment penalty", render: (q) => q.prepay_label ?? "—", investmentOnly: true },
  { label: "Monthly payment", render: (q) => formatMoneyCents(q.monthly_payment) },
  { label: "Cash to close", render: (q) => formatMoneyCents(q.cash_to_close) },
  {
    label: "Monthly cashflow",
    render: (q) => formatMoneyCents(q.monthly_cashflow),
    investmentOnly: true,
  },
  { label: "DSCR", render: (q) => q.dscr_ratio ?? "—", investmentOnly: true },
];

export function CompareTable({ quotes, strategy }: CompareTableProps) {
  const isInvestment = strategy === "LTR" || strategy === "STR";
  const rows = ROWS.filter((row) => !row.investmentOnly || isInvestment);
  return (
    <table className="w-full border-collapse text-sm">
      <thead>
        <tr className="border-b border-neutral-200 text-left text-neutral-600">
          <th scope="col" className="px-3 py-2 font-medium">
            <span className="sr-only">Row</span>
          </th>
          {quotes.map((quote) => (
            <th
              key={quote.id}
              scope="col"
              className={`px-3 py-2 text-right font-medium ${
                quote.recommended ? "bg-sage-50 text-sage-900" : ""
              }`}
            >
              {quote.label} {formatPercent(quote.rate_pct)}
              {quote.recommended && <span className="ml-1 text-sage-500">★</span>}
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
            {quotes.map((quote) => (
              <td
                key={quote.id}
                className={`num px-3 py-2 text-right text-navy-900 ${
                  quote.recommended ? "bg-sage-50" : ""
                }`}
              >
                {row.render(quote)}
              </td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );
}
