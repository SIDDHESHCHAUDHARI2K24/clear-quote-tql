import type { components } from "@cq/api-client";

import { api } from "../../../lib/api-client";

export type SettingValue = components["schemas"]["SettingValue"];

export async function fetchSettings() {
  return api.GET("/api/v1/admin/settings");
}
