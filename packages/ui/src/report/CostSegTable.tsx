import { formatMoneyPrecise, formatPercent } from "./format";
import type { CostSegTableData } from "./types";

export interface CostSegTableProps {
  costSeg: CostSegTableData;
}

/** Investment only (spec.md): price, land 20%, basis, accelerated 25%,
 * bonus %, year-1 deduction, marginal rate, savings. */
export function CostSegTable({ costSeg }: CostSegTableProps) {
  const rows: Array<{ label: string; value: string }> = [
    { label: "Purchase price", value: formatMoneyPrecise(costSeg.purchase_price) },
    {
      label: `Land allocation (${formatPercent(costSeg.land_allocation_pct)})`,
      value: formatMoneyPrecise(costSeg.land_value_allocation),
    },
    {
      label: "Depreciable building basis",
      value: formatMoneyPrecise(costSeg.depreciable_building_basis),
    },
    {
      label: `Accelerated property (${formatPercent(costSeg.accelerated_property_pct)})`,
      value: formatMoneyPrecise(costSeg.accelerated_basis_amount),
    },
    { label: "Bonus depreciation", value: formatPercent(costSeg.bonus_depreciation_pct) },
    { label: "Year-1 tax deduction", value: formatMoneyPrecise(costSeg.year_one_tax_deduction) },
    { label: "Marginal tax rate", value: formatPercent(costSeg.investor_marginal_tax_rate) },
    { label: "Year-1 tax savings", value: formatMoneyPrecise(costSeg.year_one_tax_savings) },
  ];

  return (
    <dl className="space-y-1.5 text-sm print:break-inside-avoid">
      {rows.map((row) => (
        <div key={row.label} className="flex justify-between">
          <dt className="text-neutral-600">{row.label}</dt>
          <dd className="num text-navy-900">{row.value}</dd>
        </div>
      ))}
    </dl>
  );
}
