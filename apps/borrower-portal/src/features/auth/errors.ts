// Backend error body shape (backend/app/core/errors.py):
//   {"error": {"code": "...", "message": "...", "details": {}}}
// openapi-fetch types the 401/409/429 the borrower auth endpoints can
// return as `unknown` (not documented responses in the OpenAPI schema), so
// this reads the body defensively rather than trusting a type.
interface BackendErrorBody {
  error?: {
    code?: unknown;
    message?: unknown;
    details?: unknown;
  };
}

function isBackendErrorBody(value: unknown): value is BackendErrorBody {
  return typeof value === "object" && value !== null && "error" in value;
}

// Extracts the backend's own message ("Invalid email or password", "Too
// many attempts. Try again later.", "Invalid or expired code", the 409
// "no loan officer" conflict, ...) so the UI shows exactly what the API
// decided to say, falling back only for shapes the API never actually
// sends (network failure, 500, etc).
export function extractErrorMessage(error: unknown, fallback: string): string {
  if (isBackendErrorBody(error) && typeof error.error?.message === "string") {
    return error.error.message;
  }
  return fallback;
}
