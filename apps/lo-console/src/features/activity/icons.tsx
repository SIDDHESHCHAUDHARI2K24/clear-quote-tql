// spec.md "Timeline": one icon per event-type category (import, flag,
// pricing, override, send, view, borrower action, email, consent), plus a
// system/other fallback. `override`/`consent` have no writers yet
// (plan.md CQ-029 decision 5) -- the mapping is ready for them.
const CATEGORY_ICON: Record<string, string> = {
  import: "\u{1F4E5}", // 📥
  flag: "\u{1F6A9}", // 🚩
  pricing: "\u{1F4B2}", // 💲
  override: "\u{270F}\u{FE0F}", // ✏️
  send: "\u{1F4E4}", // 📤
  view: "\u{1F441}\u{FE0F}", // 👁️
  borrower_action: "\u{1F464}", // 👤
  email: "\u{2709}\u{FE0F}", // ✉️
  consent: "\u{1F4DD}", // 📝
  system: "\u{2699}\u{FE0F}", // ⚙️
  other: "\u{2022}", // •
};

const TYPE_PREFIX_CATEGORY: Array<[string, string]> = [
  ["pipeline.imported", "import"],
  ["pipeline.verified", "flag"],
  ["pipeline.flagged", "flag"],
  ["pipeline.enriched", "pricing"],
  ["pipeline.pricing_blocked", "pricing"],
  ["pipeline.priced", "pricing"],
  ["pipeline.resumed", "pricing"],
  ["quote.sent", "send"],
  ["quote.viewed", "view"],
  ["quote.move_forward", "borrower_action"],
  ["quote.ask_other", "borrower_action"],
  ["quote.ask_updated", "borrower_action"],
  ["quote.option_selected", "borrower_action"],
  ["application.", "flag"],
  ["email.", "email"],
  ["consent.", "consent"],
  ["field.override", "override"],
  ["field.revert", "override"],
];

export function categoryForEventType(type: string): string {
  const match = TYPE_PREFIX_CATEGORY.find(([prefix]) => type.startsWith(prefix));
  return match ? match[1] : "other";
}

export function iconForEventType(type: string): string {
  return CATEGORY_ICON[categoryForEventType(type)] ?? CATEGORY_ICON.other;
}
