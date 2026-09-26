import { formatDate, formatMoneyPrecise } from "@cq/ui";

import type { FieldRowKind, FieldRowOption } from "./FieldRow";
import type { SectionField } from "./api";

/** Display-only formatting for a `SectionField.value` (already the exact
 * value the backend stored; this never computes anything, per AGENTS.md
 * "money math lives only in quote_engine"). */
export function formatFieldValue(
  field: SectionField,
  kind: FieldRowKind = "text",
  options?: FieldRowOption[],
): string {
  const { value } = field;
  if (value === null || value === undefined || value === "") return "—";
  if (Array.isArray(value)) return value.length > 0 ? value.join(", ") : "—";
  if (kind === "boolean") return value === true || value === "true" ? "Yes" : "No";
  if (kind === "money") return formatMoneyPrecise(String(value));
  if (kind === "date") {
    try {
      return formatDate(String(value));
    } catch {
      return String(value);
    }
  }
  if (kind === "select" && options) {
    return options.find((option) => option.value === String(value))?.label ?? String(value);
  }
  return String(value);
}

const ratioFormatter = new Intl.NumberFormat("en-US", {
  style: "percent",
  minimumFractionDigits: 1,
  maximumFractionDigits: 1,
});

/** `borrower_ratios.debt_to_income_ratio` returns a 0-1 fraction (plan.md
 * #10, e.g. `"0.2839"`), not a pre-scaled percent string like the report
 * package's other rate/percent fields -- this is the one place on the
 * Credit tab that reads it. `Intl.NumberFormat`'s `style: "percent"` is a
 * formatter, the same sanctioned `Number(value)` -> formatter conversion
 * `@cq/ui`'s `formatMoney`/`formatPercent` already do; it never combines
 * two values or rounds a business figure itself. */
export function formatDtiRatio(value: string): string {
  return ratioFormatter.format(Number(value));
}
