import { describe, expect, it } from "vitest";

import { categoryForEventType, iconForEventType } from "./icons";

// M2 (review round 1): field.edited/field.reverted/field.auto_updated,
// flag.*, credit.*, support.*, row.*, ssn.*, document.*, property.*,
// application.stale and application.repriced_from_stale used to fall
// through to the generic "other" bullet icon.
describe("categoryForEventType (M2)", () => {
  it.each([
    ["field.edited", "override"],
    ["field.reverted", "override"],
    ["field.auto_updated", "override"],
    ["flag.raised", "flag"],
    ["flag.resolved", "flag"],
    ["credit.liabilities_imported", "credit"],
    ["credit.hard_pull_requested", "credit"],
    ["support.requested", "support"],
    ["row.added", "override"],
    ["ssn.revealed", "sensitive"],
    ["document.received", "document"],
    ["property.updated", "property"],
    ["application.stale", "flag"],
    ["application.repriced_from_stale", "pricing"],
    ["application.submitted", "borrower_action"],
    ["pipeline.resume_requested", "pricing"],
    ["pipeline.resume_failed", "pricing"],
    ["quotes.marked_stale", "flag"],
    ["quotes.repriced", "pricing"],
    ["quote.recommended", "pricing"],
    ["quote.deleted", "pricing"],
    ["scenario.updated", "pricing"],
    ["scenario.autoquoted", "pricing"],
  ])("maps %s to the %s category, not 'other'", (type, expected) => {
    expect(categoryForEventType(type)).toBe(expected);
  });

  it("still falls back to 'other' for a genuinely unknown type", () => {
    expect(categoryForEventType("something.unmapped")).toBe("other");
  });

  it("returns a non-bullet icon for every newly-mapped type", () => {
    for (const type of [
      "field.edited",
      "flag.raised",
      "credit.liabilities_imported",
      "support.requested",
      "row.added",
      "ssn.revealed",
      "document.received",
      "property.updated",
    ]) {
      expect(iconForEventType(type)).not.toBe("\u{2022}");
    }
  });

  // Code review round 2: a plain "first entry in the array wins" match
  // made a type's category depend on its position relative to any of its
  // own prefixes already in the array -- a future specific entry appended
  // after a broader one (e.g. "application.") would be silently shadowed.
  // The three already-listed exact types under the generic "application."
  // prefix above are the existing proof this matters; these two assert
  // the general rule (longest prefix, not array order) holds for a type
  // that isn't specially listed at all.
  it("prefers the longest matching prefix over array order", () => {
    // "application." (a broad, early prefix) is a prefix of every one of
    // these, but the specific "application.submitted" entry -- listed
    // after several other prefixes in the array -- still wins because it
    // is the longer match.
    expect(categoryForEventType("application.submitted")).toBe("borrower_action");
    expect(categoryForEventType("application.submitted")).not.toBe(
      categoryForEventType("application.something_else_unlisted"),
    );
  });
});
