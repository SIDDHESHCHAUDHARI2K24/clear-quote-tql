import { describe, expect, it } from "vitest";

import { placeholder } from "./index";

describe("placeholder", () => {
  it("keeps the test runner green until CQ-004/CQ-005 generate the real client", () => {
    expect(placeholder).toBe(true);
  });
});
