import { createApiClient } from "@cq/api-client";

// CQ-004's backend dev server is pinned to port 8000 (`make api`). Each app
// reads its own NEXT_PUBLIC_API_URL (see .env.example) and falls back to
// that default so the placeholder home page works without a .env.local.
export const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export const api = createApiClient(API_BASE_URL);
