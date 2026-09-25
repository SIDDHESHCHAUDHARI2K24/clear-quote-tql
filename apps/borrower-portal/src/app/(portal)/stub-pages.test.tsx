import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

// Moved out of `page.test.tsx` (CQ-031 review round 1 / plan.md Decision
// 8): `/` stopped being a stub once this item built the real home page,
// but `/support`, `/apply` and `/tasks/credit-check/[id]` are still the
// P5/P6 foundation's placeholders for CQ-034/032b/033 respectively. Their
// coverage moves here unchanged so those items keep a green test without
// this item's PR touching files it doesn't own.
import SupportPage from "./support/page";
import ApplyPage from "./apply/page";
import CreditCheckTaskPage from "./tasks/credit-check/[id]/page";

describe("(portal) stub pages", () => {
  it.each([
    ["Support", SupportPage, "CQ-034"],
    ["Apply", ApplyPage, "CQ-032"],
    ["Credit check", CreditCheckTaskPage, "CQ-033"],
  ])("%s says which item builds it", (title, Page, item) => {
    render(<Page />);
    expect(screen.getByRole("heading", { level: 1, name: title })).toBeInTheDocument();
    expect(screen.getByText(`Built in ${item}`)).toBeInTheDocument();
  });
});
