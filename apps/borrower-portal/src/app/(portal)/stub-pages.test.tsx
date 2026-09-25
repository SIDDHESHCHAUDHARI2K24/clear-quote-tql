import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

// Moved out of `page.test.tsx` (CQ-031 review round 1 / plan.md Decision
// 8): `/` stopped being a stub once this item built the real home page,
// but `/tasks/credit-check/[id]` is still the P5/P6 foundation's
// placeholder for CQ-033. Its coverage moves here unchanged so that item
// keeps a green test without this item's PR touching files it doesn't own.
//
// `/support` and `/apply` are no longer listed here: CQ-034 and CQ-032
// built their real forms (no longer stubs) -- their own tests live in
// `src/features/support/SupportForm.test.tsx` and
// `src/features/apply/ApplyWizard.validation.test.tsx`.
import CreditCheckTaskPage from "./tasks/credit-check/[id]/page";

describe("(portal) stub pages", () => {
  it.each([["Credit check", CreditCheckTaskPage, "CQ-033"]])(
    "%s says which item builds it",
    (title, Page, item) => {
      render(<Page />);
      expect(screen.getByRole("heading", { level: 1, name: title })).toBeInTheDocument();
      expect(screen.getByText(`Built in ${item}`)).toBeInTheDocument();
    },
  );
});
