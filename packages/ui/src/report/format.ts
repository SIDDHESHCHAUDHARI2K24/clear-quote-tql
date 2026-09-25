// Display-only formatting for the decimal-string fields `ReportViewModel`
// carries. `Number(value)` is a type coercion for `Intl.NumberFormat`, not
// arithmetic -- see report-no-money-math.test.ts (CQ-021 AC5), which scans
// this whole directory for `+ - * /` applied to money/rate/percent values
// and allow-lists this file's `Number()` calls as the one sanctioned
// conversion (feeding a formatter, never combining two values).

const moneyFormatter = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  minimumFractionDigits: 0,
  maximumFractionDigits: 0,
});

const moneyPreciseFormatter = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

/** Whole-dollar display, e.g. `"1913.05"` -> `"$1,913"`. For hero tiles and
 * anywhere a glanceable, rounded figure reads better than exact cents. */
export function formatMoney(value: string): string {
  return moneyFormatter.format(Number(value));
}

/** Cents-precise display, e.g. `"1913.05"` -> `"$1,913.05"`. For breakdown,
 * cashflow and cost-seg tables, where the exact figure matters. */
export function formatMoneyPrecise(value: string): string {
  return moneyPreciseFormatter.format(Number(value));
}

/** A rate/percent decimal string is already scaled and rounded server-side
 * (backend/app/features/quotes/report/builder.py's `_rate_pct`/`_pct_2dp`) --
 * this only appends the `%` sign, it does not scale or round. */
export function formatPercent(value: string): string {
  return `${value}%`;
}

export function formatDate(isoDate: string): string {
  const [year, month, day] = isoDate.split("-").map(Number);
  if (!year || !month || !day) return isoDate;
  const date = new Date(Date.UTC(year, month - 1, day));
  return new Intl.DateTimeFormat("en-US", {
    year: "numeric",
    month: "long",
    day: "numeric",
    timeZone: "UTC",
  }).format(date);
}

/** True when a money decimal string represents a negative amount, for the
 * "red when negative" cashflow rule (system-design.md Hero numbers). String
 * comparison only -- no arithmetic. */
export function isNegative(value: string): boolean {
  return value.trim().startsWith("-");
}
