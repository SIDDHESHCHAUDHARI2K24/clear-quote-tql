import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

// Moved out of `page.test.tsx` (CQ-031 review round 1 / plan.md Decision
// 8): `/` stopped being a stub once this item built the real home page,
// but `/apply` and `/tasks/credit-check/[id]` are still the P5/P6
// foundation's placeholders for CQ-032/033 respectively. Their coverage
// moves here unchanged so those items keep a green test without this
// item's PR touching files it doesn't own.
//
// `/support` is no longer listed here: CQ-034 built the real support form
// (no longer a stub) -- its own tests live in
// `src/features/support/SupportForm.test.tsx`. Likewise CQ-033 built
// `/tasks/credit-check/[id]` (tests in `src/features/credit-consent/`).
import ApplyPage from "./apply/page";

describe("(portal) stub pages", () => {
  it.each([["Apply", ApplyPage, "CQ-032"]])("%s says which item builds it", (title, Page, item) => {
    render(<Page />);
    expect(screen.getByRole("heading", { level: 1, name: title })).toBeInTheDocument();
    expect(screen.getByText(`Built in ${item}`)).toBeInTheDocument();
  });
});
