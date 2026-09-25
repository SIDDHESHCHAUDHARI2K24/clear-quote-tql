import { describe, expect, it } from "vitest";

import { extractErrorMessage } from "./errors";

const FALLBACK = "Something went wrong. Try again.";

describe("extractErrorMessage", () => {
  it("(a) reads the app's own error envelope's message", () => {
    const error = { error: { code: "AUTHENTICATION_ERROR", message: "Invalid email or password" } };
    expect(extractErrorMessage(error, FALLBACK)).toBe("Invalid email or password");
  });

  it("(b) reads the first FastAPI validation detail's msg, stripping a 'Value error, ' prefix", () => {
    const error = {
      detail: [
        { loc: ["body", "full_name"], msg: "Value error, must not be blank", type: "value_error" },
      ],
    };
    expect(extractErrorMessage(error, FALLBACK)).toBe("must not be blank");
  });

  it("(b) keeps a FastAPI validation detail's msg as-is when there is no 'Value error, ' prefix", () => {
    const error = {
      detail: [
        { loc: ["body", "email"], msg: "value is not a valid email address", type: "value_error" },
      ],
    };
    expect(extractErrorMessage(error, FALLBACK)).toBe("value is not a valid email address");
  });

  it("(b) falls back to a friendly field name from loc when the detail has no msg", () => {
    const error = { detail: [{ loc: ["body", "full_name"] }] };
    expect(extractErrorMessage(error, FALLBACK)).toBe("Full name is invalid.");
  });

  it("(c) reads `detail` as a plain string", () => {
    const error = { detail: "Not authenticated" };
    expect(extractErrorMessage(error, FALLBACK)).toBe("Not authenticated");
  });

  it("(d) falls back for a network failure (undefined)", () => {
    expect(extractErrorMessage(undefined, FALLBACK)).toBe(FALLBACK);
  });

  it("(d) falls back for an empty object", () => {
    expect(extractErrorMessage({}, FALLBACK)).toBe(FALLBACK);
  });

  it("(d) falls back when `error` is present but not an object", () => {
    // The bug this guards against: `isAppErrorBody` used to accept any
    // value with an "error" key, including one whose `error` isn't itself
    // an object.
    expect(extractErrorMessage({ error: "boom" }, FALLBACK)).toBe(FALLBACK);
  });

  it("(d) falls back when the detail array is empty", () => {
    expect(extractErrorMessage({ detail: [] }, FALLBACK)).toBe(FALLBACK);
  });

  it("(d) falls back for a plain string error", () => {
    expect(extractErrorMessage("network error", FALLBACK)).toBe(FALLBACK);
  });
});
