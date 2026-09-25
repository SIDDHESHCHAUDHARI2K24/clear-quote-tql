import type { components } from "@cq/api-client";

// spec.md CQ-027 "Backend" / plan.md E9: the shared row shape CQ-026
// reuses directly rather than redefining.
export type ApplicationListRow = components["schemas"]["ApplicationRow"];
export type ApplicationListResponse = components["schemas"]["ApplicationListResponse"];
export type LoOption = components["schemas"]["LoOption"];
export type ApplicationStatusValue = components["schemas"]["ApplicationStatus"];
export type ApplicationStrategyValue = ApplicationListRow["strategy"];
