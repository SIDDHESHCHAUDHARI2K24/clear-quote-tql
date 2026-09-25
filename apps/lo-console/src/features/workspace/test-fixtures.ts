import type { ApplicationSummary } from "./api";

// Shared base fixture for the workspace tests -- spread + override per test
// (AC2/AC3's Priya Nair / Marcus Hale shapes, etc).
export function makeSummary(overrides: Partial<ApplicationSummary> = {}): ApplicationSummary {
  return {
    application_id: "11111111-1111-1111-1111-111111111111",
    client_name: "Priya Nair",
    status: "priced",
    last_pipeline_stage: "priced",
    occupancy: "primary",
    strategy: null,
    program: "Conventional 30 YR Fixed",
    location: { city: "Austin", state: "TX", zip: "78701" },
    purchasing_power: "450000.00",
    down_payment_pct: "0.20",
    down_payment_amount: "90000.00",
    ppp_years: null,
    note_rate: null,
    tabs: [
      { tab: "borrowers", state: "ok", flag_count: 0 },
      { tab: "housing", state: "ok", flag_count: 0 },
      { tab: "credit", state: "ok", flag_count: 0 },
      { tab: "assets", state: "ok", flag_count: 0 },
      { tab: "property", state: "ok", flag_count: 0 },
      { tab: "pricing", state: "ok", flag_count: 0 },
      { tab: "send", state: "pending", flag_count: 0 },
    ],
    default_tab: "pricing",
    ...overrides,
  };
}
