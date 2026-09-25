import { describe, expect, it } from "vitest";

import { placeholder } from "./index";

describe("placeholder", () => {
  it("keeps the test runner green until CQ-005 adds real components", () => {
    expect(placeholder).toBe(true);
  });
});
