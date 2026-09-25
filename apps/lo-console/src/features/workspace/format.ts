// Decimal fields serialize as JSON strings over the wire (pydantic v2's
// default), so every header number needs parsing before it can be
// formatted. These are display-only conversions -- no money math happens
// here (AGENTS.md: money math lives only in `quote_engine`).

function toNumber(value: string | null | undefined): number | null {
  if (value === null || value === undefined) return null;
  const n = Number(value);
  return Number.isFinite(n) ? n : null;
}

const moneyFormatter = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  maximumFractionDigits: 0,
});

export function formatMoney(value: string | null | undefined): string {
  const n = toNumber(value);
  return n === null ? "—" : moneyFormatter.format(n);
}

// `down_payment_pct` is a 0-1 fraction like every other engine `*_pct`
// field (e.g. "0.25" -> "25%").
export function formatPercent(value: string | null | undefined): string {
  const n = toNumber(value);
  return n === null ? "—" : `${(n * 100).toFixed(0)}%`;
}

// `note_rate` (`Quote.rate`) is already percent-scale (e.g. "7.500" means
// 7.500%, not a 0-1 fraction -- see `pricing/scenarios/dscr_loop.py`).
export function formatRate(value: string | null | undefined): string {
  const n = toNumber(value);
  return n === null ? "—" : `${n.toFixed(3)}%`;
}

export function formatPpp(years: number | null | undefined): string {
  if (years === null || years === undefined) return "—";
  return years === 0 ? "None" : `${years}y PPP`;
}
