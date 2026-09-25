import type { components } from "@cq/api-client";

import { api } from "../../lib/api-client";

export type SupportTopic = components["schemas"]["SupportTopic"];
export type PreferredContact = components["schemas"]["PreferredContact"];
export type SupportRequestResponse = components["schemas"]["SupportRequestResponse"];

export const SUPPORT_TOPICS: { value: SupportTopic; label: string }[] = [
  { value: "application", label: "My application" },
  { value: "quote", label: "My quote" },
  { value: "documents", label: "Documents" },
  { value: "other", label: "Something else" },
];

export async function submitSupportRequest(body: {
  topic: SupportTopic;
  message: string;
  preferred_contact: PreferredContact;
  phone?: string;
}) {
  return api.POST("/api/v1/portal/support", { body });
}
