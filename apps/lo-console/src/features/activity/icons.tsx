// spec.md "Timeline": one icon per event-type category (import, flag,
// pricing, override, send, view, borrower action, email, consent), plus a
// system/other fallback. `consent` has no writer yet (plan.md CQ-029
// decision 5) -- the mapping is ready for it. `credit`, `support`,
// `sensitive`, `document` and `property` cover the CQ-028a
// (applications/sections) and CQ-030 (stale) event types (M2 fix).
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
  credit: "\u{1F4B3}", // 💳
  support: "\u{1F198}", // 🆘
  sensitive: "\u{1F512}", // 🔒
  document: "\u{1F4C4}", // 📄
  property: "\u{1F3E0}", // 🏠
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
  ["pipeline.resume_requested", "pricing"],
  ["pipeline.resume_failed", "pricing"],
  ["quote.sent", "send"],
  ["quote.viewed", "view"],
  ["quote.move_forward", "borrower_action"],
  ["quote.ask_other", "borrower_action"],
  ["quote.ask_updated", "borrower_action"],
  ["quote.option_selected", "borrower_action"],
  ["application.stale", "flag"],
  // U3 (P5/P6 merge): the CQ-017/018 quote-builder events.
  ["quotes.marked_stale", "flag"],
  ["quotes.repriced", "pricing"],
  ["quote.recommended", "pricing"],
  ["quote.deleted", "pricing"],
  ["scenario.", "pricing"],
  ["application.repriced_from_stale", "pricing"],
  ["application.submitted", "borrower_action"],
  ["application.", "flag"],
  ["email.", "email"],
  ["consent.", "consent"],
  ["field.edited", "override"],
  ["field.reverted", "override"],
  ["field.auto_updated", "override"],
  ["row.added", "override"],
  ["flag.raised", "flag"],
  ["flag.resolved", "flag"],
  ["credit.", "credit"],
  ["support.", "support"],
  ["ssn.", "sensitive"],
  ["document.", "document"],
  ["property.", "property"],
];

export function categoryForEventType(type: string): string {
  // Longest matching prefix wins, not "first in the array" (code review
  // round 2): a plain first-match `.find()` made every entry's category
  // depend on its position relative to any prefix of it already in the
  // array (e.g. a future `application.reopened` entry appended at the end,
  // after the generic `application.` catch-all above, would silently be
  // shadowed by it). Longest-prefix matching is correct regardless of
  // where a new specific entry is added.
  let bestCategory = "other";
  let bestLength = -1;
  for (const [prefix, category] of TYPE_PREFIX_CATEGORY) {
    if (type.startsWith(prefix) && prefix.length > bestLength) {
      bestCategory = category;
      bestLength = prefix.length;
    }
  }
  return bestCategory;
}

export function iconForEventType(type: string): string {
  return CATEGORY_ICON[categoryForEventType(type)] ?? CATEGORY_ICON.other;
}
