/**
 * Tiny dotted-path helpers over the loosely-typed tab `data` record (the
 * draft's `data.<tab>` JSON, per CQ-032 plan.md's "Per-tab data contract").
 * Every leaf scalar the server validates is either a string, a boolean, or
 * a string array; pydantic coerces a numeric-looking string (e.g.
 * `"3"` for `dependents_count`) itself (lax int/Decimal parsing), so the
 * UI never needs to convert -- every text/number input's value is read and
 * written as a plain string, keeping "the frontend never computes money"
 * (system-design.md) trivially true here too.
 */

export type JsonRecord = Record<string, unknown>;

function isRecord(value: unknown): value is JsonRecord {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

/** Immutably sets a dotted path (e.g. `"current_address.zip"`), creating
 * any missing intermediate objects. */
export function setPath(obj: JsonRecord, path: string, value: unknown): JsonRecord {
  const dot = path.indexOf(".");
  if (dot === -1) return { ...obj, [path]: value };
  const head = path.slice(0, dot);
  const rest = path.slice(dot + 1);
  const child = isRecord(obj[head]) ? obj[head] : {};
  return { ...obj, [head]: setPath(child, rest, value) };
}

export function getPath(obj: JsonRecord, path: string): unknown {
  return path.split(".").reduce<unknown>((acc, key) => {
    if (isRecord(acc)) return acc[key];
    return undefined;
  }, obj);
}

export function getString(obj: JsonRecord, path: string): string {
  const value = getPath(obj, path);
  if (typeof value === "string") return value;
  if (typeof value === "number") return String(value);
  return "";
}

export function getBool(obj: JsonRecord, path: string, fallback = false): boolean {
  const value = getPath(obj, path);
  return typeof value === "boolean" ? value : fallback;
}

export function getStringArray(obj: JsonRecord, path: string): string[] {
  const value = getPath(obj, path);
  return Array.isArray(value)
    ? value.filter((item): item is string => typeof item === "string")
    : [];
}
