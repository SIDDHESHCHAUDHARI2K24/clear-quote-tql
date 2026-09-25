import type { paths } from "@cq/api-client";

import { api } from "../../lib/api-client";

export type ClientListQuery = NonNullable<paths["/api/v1/clients"]["get"]["parameters"]["query"]>;

export async function fetchClients(query: ClientListQuery) {
  return api.GET("/api/v1/clients", { params: { query } });
}

export async function fetchClient(clientId: string) {
  return api.GET("/api/v1/clients/{client_id}", { params: { path: { client_id: clientId } } });
}
