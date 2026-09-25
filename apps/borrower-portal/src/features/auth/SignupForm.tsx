"use client";

import { useState } from "react";
import type { FormEvent } from "react";

import { Button } from "@cq/ui";

import { extractErrorMessage } from "./errors";
import { api } from "../../lib/api-client";

const GENERIC_ERROR = "Something went wrong. Try again.";
// Mirrors backend/app/features/auth/users/service.py's MIN_PASSWORD_LENGTH.
// Not exposed via the OpenAPI schema (schemas.py's password field has no
// `min_length`), so this is a duplicated constant, not a generated one —
// if the backend minimum ever changes, update this too. It's only a UX
// short-circuit either way: the server is the actual source of truth and
// still enforces its own minimum via a 422 on `/signup`.
const MIN_PASSWORD_LENGTH = 8;

export interface SignupFormProps {
  // Called once the API has issued an OTP challenge for `email`. Per
  // plan.md Decision #5, this fires the same way whether or not the email
  // already has an account — the caller can't tell the difference.
  onChallenge: (challengeId: string, email: string) => void;
}

export function SignupForm({ onChallenge }: SignupFormProps) {
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);

    // Client-side checks first so a mismatched/short password never makes
    // a round trip — the backend still enforces the minimum length (422).
    if (password.length < MIN_PASSWORD_LENGTH) {
      setError(`Password must be at least ${MIN_PASSWORD_LENGTH} characters.`);
      return;
    }

    if (password !== confirmPassword) {
      setError("Passwords do not match.");
      return;
    }

    setPending(true);

    try {
      const { data, error: apiError } = await api.POST("/api/v1/auth/borrower/signup", {
        body: { full_name: fullName, email, password },
      });

      if (!data) {
        setError(extractErrorMessage(apiError, GENERIC_ERROR));
        return;
      }

      onChallenge(data.challenge_id, email);
    } catch {
      setError(GENERIC_ERROR);
    } finally {
      setPending(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} noValidate className="flex flex-col gap-4">
      <div className="flex flex-col gap-1">
        <label htmlFor="signup-full-name" className="text-sm font-medium text-navy-900">
          Full name
        </label>
        <input
          id="signup-full-name"
          name="full_name"
          type="text"
          autoComplete="name"
          required
          value={fullName}
          disabled={pending}
          onChange={(event) => setFullName(event.target.value)}
          className="rounded-md border border-neutral-200 bg-neutral-0 px-3 py-2 text-navy-900 outline-none focus:border-navy-500 disabled:opacity-50"
        />
      </div>

      <div className="flex flex-col gap-1">
        <label htmlFor="signup-email" className="text-sm font-medium text-navy-900">
          Email
        </label>
        <input
          id="signup-email"
          name="email"
          type="email"
          autoComplete="username"
          required
          value={email}
          disabled={pending}
          onChange={(event) => setEmail(event.target.value)}
          className="rounded-md border border-neutral-200 bg-neutral-0 px-3 py-2 text-navy-900 outline-none focus:border-navy-500 disabled:opacity-50"
        />
      </div>

      <div className="flex flex-col gap-1">
        <label htmlFor="signup-password" className="text-sm font-medium text-navy-900">
          Password
        </label>
        <input
          id="signup-password"
          name="password"
          type="password"
          autoComplete="new-password"
          required
          value={password}
          disabled={pending}
          onChange={(event) => setPassword(event.target.value)}
          className="rounded-md border border-neutral-200 bg-neutral-0 px-3 py-2 text-navy-900 outline-none focus:border-navy-500 disabled:opacity-50"
        />
        <p className="text-xs text-neutral-500">At least {MIN_PASSWORD_LENGTH} characters.</p>
      </div>

      <div className="flex flex-col gap-1">
        <label htmlFor="signup-confirm-password" className="text-sm font-medium text-navy-900">
          Confirm password
        </label>
        <input
          id="signup-confirm-password"
          name="confirm_password"
          type="password"
          autoComplete="new-password"
          required
          value={confirmPassword}
          disabled={pending}
          onChange={(event) => setConfirmPassword(event.target.value)}
          className="rounded-md border border-neutral-200 bg-neutral-0 px-3 py-2 text-navy-900 outline-none focus:border-navy-500 disabled:opacity-50"
        />
      </div>

      {error && (
        <p role="alert" className="text-sm text-status-danger">
          {error}
        </p>
      )}

      <Button type="submit" disabled={pending} isLoading={pending}>
        Create account
      </Button>
    </form>
  );
}
