import { describe, it } from "vitest";

// Moved out of `page.test.tsx` (CQ-031 review round 1 / plan.md Decision
// 8): `/` stopped being a stub once this item built the real home page.
//
// `/support`, `/tasks/credit-check/[id]` and `/apply` are no longer listed
// here: CQ-034, CQ-033 and CQ-032 built their real forms (no longer
// stubs) -- their own tests live in `src/features/support/SupportForm.test.tsx`,
// `src/features/credit-consent/CreditConsent.test.tsx` and
// `src/features/apply/ApplyWizard.validation.test.tsx`.

describe("(portal) stub pages", () => {
  it.skip("no stub pages remain to test", () => {
    // Placeholder retained so this file stays a valid, discoverable test
    // suite if a future item introduces another stub page.
  });
});
