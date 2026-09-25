"use client";

import { useState } from "react";
import type { FormEvent } from "react";

import { Button } from "@cq/ui";

import { extractErrorMessage } from "./errors";
import { api } from "../../lib/api-client";

const GENERIC_ERROR = "Something went wrong. Try again.";

export interface LoginFormProps {
  // Called once the API has issued an OTP challenge for `email`.
  onChallenge: (challengeId: string, email: string) => void;
}

export function LoginForm({ onChallenge }: LoginFormProps) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setPending(true);

    try {
      const { data, error: apiError } = await api.POST("/api/v1/auth/staff/login", {
        body: { email, password },
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
        <label htmlFor="login-email" className="text-sm font-medium text-navy-900">
          Email
        </label>
        <input
          id="login-email"
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
        <label htmlFor="login-password" className="text-sm font-medium text-navy-900">
          Password
        </label>
        <input
          id="login-password"
          name="password"
          type="password"
          autoComplete="current-password"
          required
          value={password}
          disabled={pending}
          onChange={(event) => setPassword(event.target.value)}
          className="rounded-md border border-neutral-200 bg-neutral-0 px-3 py-2 text-navy-900 outline-none focus:border-navy-500 disabled:opacity-50"
        />
      </div>

      {error && (
        <p role="alert" className="text-sm text-status-danger">
          {error}
        </p>
      )}

      <Button type="submit" disabled={pending} isLoading={pending}>
        Sign in
      </Button>
    </form>
  );
}
