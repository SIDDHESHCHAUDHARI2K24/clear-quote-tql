import type { components } from "@cq/api-client";

import { api } from "../../lib/api-client";

export type SendPackage = components["schemas"]["PackageRead"];
export type PackageUpdate = components["schemas"]["PackageUpdate"];
export type Readiness = components["schemas"]["PackageReadiness"];
export type ReadinessBlocker = components["schemas"]["ReadinessBlocker"];
export type ReportViewModel = components["schemas"]["ReportViewModel"];

export type Loaded<T> = { ok: true; data: T } | { ok: false; message: string };

interface ErrorEnvelope {
  error?: { message?: string };
}

async function settle<T>(
  call: Promise<{ data?: T; error?: unknown; response: Response }>,
): Promise<Loaded<T>> {
  try {
    const { data, error, response } = await call;
    if (!response.ok || error !== undefined || data === undefined) {
      const message = (error as ErrorEnvelope | undefined)?.error?.message;
      return { ok: false, message: message ?? "Something went wrong. Try again." };
    }
    return { ok: true, data };
  } catch {
    return { ok: false, message: "Something went wrong. Try again." };
  }
}

export function fetchPackage(applicationId: string) {
  return settle(
    api.GET("/api/v1/applications/{application_id}/package", {
      params: { path: { application_id: applicationId } },
    }),
  );
}

export function savePackage(applicationId: string, body: PackageUpdate) {
  return settle(
    api.PUT("/api/v1/applications/{application_id}/package", {
      params: { path: { application_id: applicationId } },
      body,
    }),
  );
}

export function fetchReadiness(packageId: string) {
  return settle(
    api.GET("/api/v1/packages/{package_id}/readiness", {
      params: { path: { package_id: packageId } },
    }),
  );
}

export function fetchReport(packageId: string) {
  return settle(
    api.GET("/api/v1/packages/{package_id}/report", {
      params: { path: { package_id: packageId } },
    }),
  );
}

/** The letter's HTML, rendered into a script-less `<iframe sandbox="">`. */
export function fetchLetterHtml(packageId: string) {
  return settle<string>(
    api.GET("/api/v1/packages/{package_id}/letter.html", {
      params: { path: { package_id: packageId } },
      parseAs: "text",
    }) as Promise<{ data?: string; error?: unknown; response: Response }>,
  );
}
