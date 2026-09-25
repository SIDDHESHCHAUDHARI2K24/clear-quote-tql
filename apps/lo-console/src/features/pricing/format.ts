// Display-only formatting of API-returned decimal strings. No arithmetic on
// a money/rate value happens here or anywhere else in this feature --
// AGENTS.md: money math lives only in `quote_engine`; see
// `pricing-no-money-math.test.ts`'s scan, which excludes this file the same
// way CQ-021's `report/format.ts` is excluded from its own scan.
//
// `toNumber` is a near-duplicate of `features/workspace/format.ts`'s own
// (unexported) helper of the same name -- not reused because that one is
// private, and exporting it would mean editing a file this item doesn't
// own (CQ-016) for a 4-line function. Kept local; logged in plan.md.
import { formatMoneyPrecise } from "@cq/ui";

function toNumber(value: string | null | undefined): number | null {
  if (value === null || value === undefined || value === "") return null;
  const n = Number(value);
  return Number.isFinite(n) ? n : null;
}

// AC1: "$273,600.00" -- always 2dp, unlike the workspace header's 0dp
// `formatMoney`. Thin null-handling wrapper around `@cq/ui`'s own
// `formatMoneyPrecise` (byte-for-byte the same cents-precise formatter
// CQ-021's report already uses) instead of a second local
// `Intl.NumberFormat` instance.
export function formatMoneyCents(value: string | null | undefined): string {
  const n = toNumber(value);
  return n === null ? "—" : formatMoneyPrecise(value as string);
}

// `*_pct` fields are 0-1 fractions (e.g. "0.80" -> "80.00%"); AC1 wants 2dp.
export function formatPercent2dp(value: string | null | undefined): string {
  const n = toNumber(value);
  return n === null ? "—" : `${(n * 100).toFixed(2)}%`;
}

// `PricingViewResponse.note_rate` is a 0-1 fraction, same scale as every
// other engine `*_pct` field (e.g. "0.075" -> "7.500%") -- NOT the same
// scale as the backend's internal `Quote.rate` column, which this feature
// never reads directly.
export function formatRate3dp(value: string | null | undefined): string {
  const n = toNumber(value);
  return n === null ? "—" : `${(n * 100).toFixed(3)}%`;
}

export function formatDscr2dp(value: string | null | undefined): string {
  const n = toNumber(value);
  return n === null ? "—" : n.toFixed(2);
}

export type DscrTone = "green" | "neutral" | "amber";

// spec.md: >= 1.25 green, 1.00-1.24 neutral, < 1.00 amber.
export function dscrTone(value: string | null | undefined): DscrTone | null {
  const n = toNumber(value);
  if (n === null) return null;
  if (n >= 1.25) return "green";
  if (n >= 1.0) return "neutral";
  return "amber";
}

// `PercentInput` (packages/ui) is percent-unit text (its own contract:
// "value/onChange are decimal strings in percent units, e.g. '7.500' =
// 7.5%"), while every `*_pct`/`*_annual_rate` field this API returns or
// accepts is a 0-1 fraction (e.g. "0.075"). These two functions are the
// single place that translates between the input control's display unit
// and the wire format -- a unit conversion of the control's own contract,
// not a derived financial figure (nothing here combines two money/rate
// API values together; see AGENTS.md's money-math rule and this
// directory's `pricing-no-money-math.test.ts`).
export function fractionToPercentInputValue(value: string | null | undefined): string {
  const n = toNumber(value);
  return n === null ? "" : (n * 100).toFixed(3);
}

export function percentInputValueToFraction(percentText: string): string {
  if (percentText === "") return "";
  const n = Number(percentText);
  return Number.isFinite(n) ? (n / 100).toFixed(4) : "";
}
