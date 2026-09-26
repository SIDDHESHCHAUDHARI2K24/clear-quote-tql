import type { SectionResponse } from "./api";

// Shared base fixture for verification-tab tests -- spread + override per
// test/tab, same pattern as workspace/test-fixtures.ts's `makeSummary`.
export function makeSection(overrides: Partial<SectionResponse> = {}): SectionResponse {
  return {
    application_id: "11111111-1111-1111-1111-111111111111",
    tab: "borrowers",
    status: "needs_attention",
    occupancy: "primary",
    records: [],
    flags: [],
    ...overrides,
  };
}
