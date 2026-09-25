import { Card } from "../components/Card";
import { cx } from "../utils/cx";
import { formatMoney, formatPercent } from "./format";
import type { ReportOptionData, ReportStrategyData } from "./types";

export interface ExplainerCardsProps {
  option: ReportOptionData;
  strategy: ReportStrategyData;
}

/**
 * Investment only: "Why the rental income works" (rent vs payment, DSCR) and
 * "Estimated year-one tax savings" with "Estimate only, not tax advice"
 * (spec.md; system-design.md Quote report step 5). Renders nothing for
 * primary -- callers may still mount it unconditionally.
 */
interface Row {
  label: string;
  value: string;
  emphasis?: boolean;
}

function RowList({ rows }: { rows: Row[] }) {
  return (
    <dl className="space-y-2 text-sm">
      {rows.map((row) => (
        <div
          key={row.label}
          className={cx(
            "flex justify-between",
            row.emphasis && "border-t border-neutral-200 pt-2 font-medium",
          )}
        >
          <dt className={row.emphasis ? "text-navy-900" : "text-neutral-600"}>{row.label}</dt>
          <dd className="num text-navy-900">{row.value}</dd>
        </div>
      ))}
    </dl>
  );
}

export function ExplainerCards({ option, strategy }: ExplainerCardsProps) {
  if (strategy === "primary" || !option.cashflow) return null;

  const rentalRows: Row[] = [
    { label: option.cashflow.rent_label, value: formatMoney(option.cashflow.qualifying_rent) },
    { label: "Total monthly payment", value: formatMoney(option.cashflow.pitia) },
    { label: "DSCR", value: option.cashflow.dscr, emphasis: true },
  ];

  const taxRows: Row[] = [
    {
      label: "Estimated deduction",
      value: option.cost_seg ? formatMoney(option.cost_seg.year_one_tax_deduction) : "—",
    },
    {
      label: "Estimated tax savings",
      value: option.hero.year1_tax_savings ? formatMoney(option.hero.year1_tax_savings) : "—",
      emphasis: true,
    },
  ];
  if (option.cost_seg) {
    taxRows.push({
      label: "At marginal rate",
      value: formatPercent(option.cost_seg.investor_marginal_tax_rate),
    });
  }

  return (
    <div className="grid gap-4 sm:grid-cols-2">
      <Card title="Why the rental income works">
        <RowList rows={rentalRows} />
      </Card>
      <Card title="Estimated year-one tax savings">
        <RowList rows={taxRows} />
        <p className="mt-3 text-xs text-neutral-600">Estimate only, not tax advice.</p>
      </Card>
    </div>
  );
}
