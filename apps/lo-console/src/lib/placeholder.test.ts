import { describe, expect, it } from "vitest";

import { placeholder } from "./placeholder";

describe("placeholder", () => {
  it("keeps the test runner green until CQ-005 adds real tests", () => {
    expect(placeholder).toBe(true);
  });
});
