// Two distinct error body shapes reach the auth forms:
//
// 1. The app's own error envelope (backend/app/core/errors.py):
//      {"error": {"code": "...", "message": "...", "details": {}}}
//    openapi-fetch types many of the 401/409/429 responses the auth
//    endpoints can return as `unknown` (not documented responses in the
//    OpenAPI schema), so this reads the body defensively rather than
//    trusting a type.
//
// 2. FastAPI's own request-validation 422, which the app's envelope never
//    produces and which `isAppErrorBody` alone used to miss entirely:
//      {"detail": [{"loc": [...], "msg": "...", "type": "..."}]}
//    (or, less commonly, `{"detail": "..."}` as a plain string). This is
//    what a Pydantic validator failure looks like — e.g. a whitespace-only
//    `full_name` on sign-up — since it never reaches the app's own error
//    handler.

interface AppErrorBody {
  error?: {
    code?: unknown;
    message?: unknown;
    details?: unknown;
  };
}

function isAppErrorBody(value: unknown): value is AppErrorBody {
  if (typeof value !== "object" || value === null || !("error" in value)) return false;
  const error = (value as { error?: unknown }).error;
  // The bug this fixes: the previous guard only checked `"error" in value`,
  // so a body shaped like `{"error": "..."}` (not an object) would pass
  // here and then silently fall through when `.message` turned out to be
  // undefined. Require `error` to actually be an object (or absent).
  return error === undefined || (typeof error === "object" && error !== null);
}

interface FastApiValidationDetail {
  loc?: unknown[];
  msg?: unknown;
  type?: unknown;
}

interface FastApiValidationBody {
  detail: FastApiValidationDetail[] | string;
}

function isFastApiValidationBody(value: unknown): value is FastApiValidationBody {
  if (typeof value !== "object" || value === null || !("detail" in value)) return false;
  const { detail } = value as { detail: unknown };
  return typeof detail === "string" || Array.isArray(detail);
}

const VALUE_ERROR_PREFIX = "Value error, ";

// "full_name" -> "Full name", "confirm_password" -> "Confirm password".
function fieldLabelFromLoc(loc: unknown[] | undefined): string | null {
  if (!loc || loc.length === 0) return null;
  const last = loc[loc.length - 1];
  if (typeof last !== "string" || last.length === 0) return null;

  const words = last.split("_").filter(Boolean);
  if (words.length === 0) return null;

  return words
    .map((word, index) => (index === 0 ? word[0].toUpperCase() + word.slice(1) : word))
    .join(" ");
}

function messageFromValidationDetail(detail: FastApiValidationDetail[] | string): string | null {
  if (typeof detail === "string") return detail;
  if (detail.length === 0) return null;

  const [first] = detail;
  if (typeof first.msg === "string" && first.msg.length > 0) {
    return first.msg.startsWith(VALUE_ERROR_PREFIX)
      ? first.msg.slice(VALUE_ERROR_PREFIX.length)
      : first.msg;
  }

  const field = fieldLabelFromLoc(first.loc);
  return field ? `${field} is invalid.` : null;
}

// Extracts the backend's own message ("Invalid email or password", "Too
// many attempts. Try again later.", "Invalid or expired code", a FastAPI
// 422 validation message, ...) so the UI shows exactly what the API
// decided to say, falling back only for shapes the API never actually
// sends (network failure, 500, etc).
export function extractErrorMessage(error: unknown, fallback: string): string {
  if (isAppErrorBody(error) && typeof error.error?.message === "string") {
    return error.error.message;
  }

  if (isFastApiValidationBody(error)) {
    const message = messageFromValidationDetail(error.detail);
    if (message) return message;
  }

  return fallback;
}
