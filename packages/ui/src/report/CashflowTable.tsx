import { formatMoneyPrecise, formatPercent, isNegative } from "./format";
import type { CashflowTableData } from "./types";

export interface CashflowTableProps {
  cashflow: CashflowTableData;
}

/** Investment only (spec.md): gross revenue/market rent, expense ratio,
 * qualifying rent, PITIA, monthly + annual cashflow, DSCR, cap rate,
 * cashflow incl. tax benefit. */
export function CashflowTable({ cashflow }: CashflowTableProps) {
  const rows: Array<{ label: string; value: string; tone?: "danger" }> = [
    { label: cashflow.rent_label, value: formatMoneyPrecise(cashflow.gross_amount) },
  ];
  if (cashflow.expense_ratio) {
    rows.push({ label: "Expense ratio", value: formatPercent(cashflow.expense_ratio) });
  }
  rows.push(
    { label: "Qualifying rent", value: formatMoneyPrecise(cashflow.qualifying_rent) },
    { label: "Total monthly payment (PITIA)", value: formatMoneyPrecise(cashflow.pitia) },
    {
      label: "Monthly cashflow",
      value: formatMoneyPrecise(cashflow.monthly_cashflow),
      tone: isNegative(cashflow.monthly_cashflow) ? "danger" : undefined,
    },
    {
      label: "Annual cashflow",
      value: formatMoneyPrecise(cashflow.annual_cashflow),
      tone: isNegative(cashflow.annual_cashflow) ? "danger" : undefined,
    },
    { label: "DSCR", value: cashflow.dscr },
    { label: "Cap rate", value: formatPercent(cashflow.cap_rate_pct) },
    {
      label: "Cashflow incl. tax benefit",
      value: formatMoneyPrecise(cashflow.monthly_cashflow_incl_tax),
      tone: isNegative(cashflow.monthly_cashflow_incl_tax) ? "danger" : undefined,
    },
  );

  return (
    <dl className="space-y-1.5 text-sm print:break-inside-avoid">
      {rows.map((row) => (
        <div key={row.label} className="flex justify-between">
          <dt className="text-neutral-600">{row.label}</dt>
          <dd className={`num ${row.tone === "danger" ? "text-status-danger" : "text-navy-900"}`}>
            {row.value}
          </dd>
        </div>
      ))}
    </dl>
  );
}
