import { cx } from "../utils/cx";
import { formatMoney, formatPercent, isNegative } from "./format";
import type { ReportOptionData, ReportStrategyData } from "./types";

export interface HeroNumbersProps {
  option: ReportOptionData;
  strategy: ReportStrategyData;
}

function Tile({
  label,
  value,
  sublabel,
  tone,
}: {
  label: string;
  value: string;
  sublabel?: string;
  tone?: "danger";
}) {
  return (
    <div className="rounded-lg border border-neutral-200 bg-neutral-0 p-4">
      <div className="text-sm font-medium text-neutral-600">{label}</div>
      <div
        className={cx(
          "num mt-1 text-3xl font-semibold",
          tone === "danger" ? "text-status-danger" : "text-navy-900",
        )}
      >
        {value}
      </div>
      {sublabel && <div className="num mt-1 text-sm text-neutral-600">{sublabel}</div>}
    </div>
  );
}

/**
 * 3 hero tiles for primary (payment, cash to close, loan amount + rate), 4
 * for investment (payment, cash to close, cashflow labelled LTR/STR and red
 * when negative, year-1 tax savings). system-design.md "Hero numbers".
 */
export function HeroNumbers({ option, strategy }: HeroNumbersProps) {
  const isPrimary = strategy === "primary";
  const cashflowLabel =
    strategy === "str" ? "Estimated monthly cashflow (STR)" : "Estimated monthly cashflow (LTR)";

  return (
    <div
      data-testid="hero-numbers"
      className={cx("grid gap-4", isPrimary ? "sm:grid-cols-3" : "sm:grid-cols-2 lg:grid-cols-4")}
    >
      <Tile label="Total monthly payment" value={formatMoney(option.hero.monthly_payment)} />
      <Tile label="Cash to close" value={formatMoney(option.hero.cash_to_close)} />
      {isPrimary ? (
        option.hero.loan_amount && (
          <Tile
            label="Loan amount"
            value={formatMoney(option.hero.loan_amount)}
            sublabel={`at ${formatPercent(option.rate)}`}
          />
        )
      ) : (
        <>
          {option.hero.monthly_cashflow && (
            <Tile
              label={cashflowLabel}
              value={formatMoney(option.hero.monthly_cashflow)}
              tone={isNegative(option.hero.monthly_cashflow) ? "danger" : undefined}
            />
          )}
          {option.hero.year1_tax_savings && option.hero.year1_tax_savings_monthly && (
            <Tile
              label="Estimated year-1 tax savings"
              value={formatMoney(option.hero.year1_tax_savings)}
              sublabel={`≈ ${formatMoney(option.hero.year1_tax_savings_monthly)}/mo`}
            />
          )}
        </>
      )}
    </div>
  );
}
