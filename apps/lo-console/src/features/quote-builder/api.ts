import type { components } from "@cq/api-client";

import { api } from "../../lib/api-client";

export type ScenariosView = components["schemas"]["ApplicationScenariosRead"];
export type ScenarioGroup = components["schemas"]["ScenarioGroupRead"];
export type QuoteCardData = components["schemas"]["QuoteCardRead"];
export type ProductRow = components["schemas"]["PricedProductRow-Output"];
export type ScenarioUpdate = components["schemas"]["ScenarioUpdateRequest"];
export type DscrBucket = components["schemas"]["DSCRBucket"];
export type BuilderStrategy = NonNullable<ScenariosView["strategy"]>;

/** A pricing failure the LO can act on (spec: "Cannot price: missing
 * {Field}" + a link to the tab that owns the field). */
export interface PricingProblem {
  message: string;
  field: string | null;
  tab: string | null;
}

export type Result<T> = { ok: true; data: T } | { ok: false; problem: PricingProblem };

interface ErrorEnvelope {
  error?: { code?: string; message?: string; details?: { field?: string; tab?: string } };
}

export function toProblem(error: unknown): PricingProblem {
  const envelope = (error ?? {}) as ErrorEnvelope;
  const details = envelope.error?.details ?? {};
  return {
    message: envelope.error?.message ?? "Something went wrong. Try again.",
    field: envelope.error?.code === "missing_field" ? (details.field ?? null) : null,
    tab: envelope.error?.code === "missing_field" ? (details.tab ?? null) : null,
  };
}

async function settle<T>(
  call: Promise<{ data?: T; error?: unknown; response: Response }>,
): Promise<Result<T>> {
  try {
    const { data, error, response } = await call;
    if (!response.ok || error !== undefined) return { ok: false, problem: toProblem(error) };
    return { ok: true, data: data as T };
  } catch {
    return { ok: false, problem: toProblem(null) };
  }
}

export function fetchScenarios(applicationId: string) {
  return settle(
    api.GET("/api/v1/applications/{application_id}/scenarios", {
      params: { path: { application_id: applicationId } },
    }),
  );
}

export function createScenario(
  applicationId: string,
  body: components["schemas"]["ScenarioCreateRequest"],
) {
  return settle(
    api.POST("/api/v1/applications/{application_id}/scenarios", {
      params: { path: { application_id: applicationId } },
      body,
    }),
  );
}

export function updateScenario(scenarioId: string, body: ScenarioUpdate) {
  return settle(
    api.PUT("/api/v1/scenarios/{scenario_id}", {
      params: { path: { scenario_id: scenarioId } },
      body,
    }),
  );
}

export function autoquote(scenarioId: string) {
  return settle(
    api.POST("/api/v1/scenarios/{scenario_id}/autoquote", {
      params: { path: { scenario_id: scenarioId } },
    }),
  );
}

export function fetchProducts(scenarioId: string) {
  return settle(
    api.GET("/api/v1/scenarios/{scenario_id}/products", {
      params: { path: { scenario_id: scenarioId } },
    }),
  );
}

export function chooseProduct(scenarioId: string, product: ProductRow) {
  return settle(
    api.POST("/api/v1/scenarios/{scenario_id}/quotes", {
      params: { path: { scenario_id: scenarioId } },
      body: { product, label: "Manual" },
    }),
  );
}

export function deleteQuote(quoteId: string) {
  return settle(
    api.DELETE("/api/v1/quotes/{quote_id}", {
      params: { path: { quote_id: quoteId } },
    }),
  );
}

export function recommendQuote(quoteId: string) {
  return settle(
    api.POST("/api/v1/quotes/{quote_id}/recommend", {
      params: { path: { quote_id: quoteId } },
    }),
  );
}

export function repriceApplication(applicationId: string) {
  return settle(
    api.POST("/api/v1/applications/{application_id}/reprice", {
      params: { path: { application_id: applicationId } },
    }),
  );
}
