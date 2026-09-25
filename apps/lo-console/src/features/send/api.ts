import type { components } from "@cq/api-client";

import { api, API_BASE_URL } from "../../lib/api-client";

export type SendPackage = components["schemas"]["PackageRead"];
export type PackageUpdate = components["schemas"]["PackageUpdate"];
export type Readiness = components["schemas"]["PackageReadiness"];
export type ReadinessBlocker = components["schemas"]["ReadinessBlocker"];
export type ReportViewModel = components["schemas"]["ReportViewModel"];
export type SendStarted = components["schemas"]["SendStarted"];
export type SendStatus = components["schemas"]["SendStatus"];
export type SendStep = SendStatus["status"];
export type SentVersion = components["schemas"]["SentVersion"];

/** A failure keeps the API's error `code` (e.g. `PACKAGE_NOT_READY`,
 * `SEND_IN_PROGRESS`) and, for a package that isn't ready, its blockers. */
export type Loaded<T> =
  | { ok: true; data: T }
  | { ok: false; message: string; code?: string; blockers?: ReadinessBlocker[] };

interface ErrorEnvelope {
  error?: { message?: string; code?: string; details?: { blockers?: ReadinessBlocker[] } };
}

const FALLBACK_MESSAGE = "Something went wrong. Try again.";

async function settle<T>(
  call: Promise<{ data?: T; error?: unknown; response: Response }>,
): Promise<Loaded<T>> {
  try {
    const { data, error, response } = await call;
    if (!response.ok || error !== undefined || data === undefined) {
      const envelope = (error as ErrorEnvelope | undefined)?.error;
      return {
        ok: false,
        message: envelope?.message ?? FALLBACK_MESSAGE,
        code: envelope?.code,
        blockers: envelope?.details?.blockers,
      };
    }
    return { ok: true, data };
  } catch {
    return { ok: false, message: FALLBACK_MESSAGE };
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

/** Starts the send workflow: 202 with the workflow id, or 409
 * `PACKAGE_NOT_READY` with `blockers`. */
export function startSend(packageId: string) {
  return settle(
    api.POST("/api/v1/packages/{package_id}/send", {
      params: { path: { package_id: packageId } },
    }),
  );
}

export function fetchSendStatus(packageId: string) {
  return settle(
    api.GET("/api/v1/packages/{package_id}/send-status", {
      params: { path: { package_id: packageId } },
    }),
  );
}

/** Sent versions, newest first. */
export function fetchSentVersions(packageId: string) {
  return settle(
    api.GET("/api/v1/packages/{package_id}/versions", {
      params: { path: { package_id: packageId } },
    }),
  );
}

/** `letter_url` is an API path (`/api/v1/packages/{id}/letter.pdf?version=N`);
 * a plain link to the API origin carries the staff cookie. */
export function apiHref(path: string): string {
  return `${API_BASE_URL}${path}`;
}
