"use client";

import { useState } from "react";
import type { FormEvent } from "react";

import { Button, TextField, useAsyncSubmit } from "@cq/ui";

import { api } from "../../lib/api-client";

const GENERIC_ERROR = "Something went wrong. Try again.";
// Mirrors backend/app/features/auth/users/service.py's MIN_PASSWORD_LENGTH.
// The backend schema (backend/app/features/auth/borrower/schemas.py) now
// carries this as `Field(min_length=MIN_PASSWORD_LENGTH, ...)`, so once
// `packages/api-client` regenerates it also shows up as `minLength` on the
// OpenAPI schema — but that's documentation, not a runtime check `fetch`
// enforces, so this stays a duplicated constant, not a generated one. It's
// only a UX short-circuit either way: the server is the actual source of
// truth and still enforces its own minimum via a 422 on `/signup`.
const MIN_PASSWORD_LENGTH = 8;
const MAX_FULL_NAME_LENGTH = 200;

export interface SignupFormProps {
  // Called once the API has issued an OTP challenge for `email`. Per
  // plan.md Decision #5, this fires the same way whether or not the email
  // already has an account — the caller can't tell the difference.
  onChallenge: (challengeId: string, email: string) => void;
  // Prefills the email field (CQ-022, H2: "allowing an email prefill" from
  // the login page's `?email=` link) — still fully editable.
  defaultEmail?: string;
}

export function SignupForm({ onChallenge, defaultEmail }: SignupFormProps) {
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState(defaultEmail ?? "");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [clientError, setClientError] = useState<string | null>(null);

  const { pending, error, run } = useAsyncSubmit(
    async ({
      full_name,
      email: submittedEmail,
      password: submittedPassword,
    }: {
      full_name: string;
      email: string;
      password: string;
    }) => {
      const { data, error: apiError } = await api.POST("/api/v1/auth/borrower/signup", {
        body: { full_name, email: submittedEmail, password: submittedPassword },
      });
      if (!data) return { ok: false as const, error: apiError };
      return { ok: true as const, data };
    },
    {
      fallbackError: GENERIC_ERROR,
      onSuccess: (data, { email: submittedEmail }) =>
        onChallenge(data.challenge_id, submittedEmail),
    },
  );

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setClientError(null);

    // Client-side checks first so an invalid name or a mismatched/short
    // password never makes a round trip — the backend still enforces
    // both (422).
    const trimmedFullName = fullName.trim();
    if (trimmedFullName.length < 1 || trimmedFullName.length > MAX_FULL_NAME_LENGTH) {
      setClientError(`Full name must be between 1 and ${MAX_FULL_NAME_LENGTH} characters.`);
      return;
    }

    if (password.length < MIN_PASSWORD_LENGTH) {
      setClientError(`Password must be at least ${MIN_PASSWORD_LENGTH} characters.`);
      return;
    }

    if (password !== confirmPassword) {
      setClientError("Passwords do not match.");
      return;
    }

    await run({ full_name: trimmedFullName, email, password });
  }

  const displayedError = clientError ?? error;

  return (
    <form onSubmit={handleSubmit} noValidate className="flex flex-col gap-4">
      <TextField
        id="signup-full-name"
        name="full_name"
        label="Full name"
        type="text"
        autoComplete="name"
        required
        value={fullName}
        disabled={pending}
        onChange={(event) => setFullName(event.target.value)}
      />

      <TextField
        id="signup-email"
        name="email"
        label="Email"
        type="email"
        autoComplete="username"
        required
        value={email}
        disabled={pending}
        onChange={(event) => setEmail(event.target.value)}
      />

      <TextField
        id="signup-password"
        name="password"
        label="Password"
        type="password"
        autoComplete="new-password"
        required
        value={password}
        disabled={pending}
        onChange={(event) => setPassword(event.target.value)}
        helperText={`At least ${MIN_PASSWORD_LENGTH} characters.`}
      />

      <TextField
        id="signup-confirm-password"
        name="confirm_password"
        label="Confirm password"
        type="password"
        autoComplete="new-password"
        required
        value={confirmPassword}
        disabled={pending}
        onChange={(event) => setConfirmPassword(event.target.value)}
      />

      {displayedError && (
        <p role="alert" className="text-sm text-status-danger">
          {displayedError}
        </p>
      )}

      <Button type="submit" disabled={pending} isLoading={pending}>
        Create account
      </Button>
    </form>
  );
}
