"use client";

import { useState } from "react";
import type { ChangeEvent, FormEvent } from "react";

import { Button } from "@cq/ui";

import { extractErrorMessage } from "./errors";
import { api } from "../../lib/api-client";

const GENERIC_ERROR = "Something went wrong. Try again.";
const DIGITS_ONLY = /\D/g;

export interface OtpFormProps {
  challengeId: string;
  email: string;
  // Called once the OTP has been verified and the session cookie is set.
  onSuccess: () => void;
  // "Use a different email" — restarts at the login/signup step.
  onBack: () => void;
}

// Shared by both the login and sign-up flows (AuthFlow). Per plan.md
// Decision #5, a sign-up for an email that already has an account reaches
// this exact same step with the exact same copy — there is nothing here
// that distinguishes "new account" from "existing account".
export function OtpForm({ challengeId, email, onSuccess, onBack }: OtpFormProps) {
  const [code, setCode] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  function handleCodeChange(event: ChangeEvent<HTMLInputElement>) {
    setCode(event.target.value.replace(DIGITS_ONLY, "").slice(0, 6));
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setPending(true);

    try {
      const { data, error: apiError } = await api.POST("/api/v1/auth/borrower/otp/verify", {
        body: { challenge_id: challengeId, code },
      });

      if (!data) {
        setError(extractErrorMessage(apiError, GENERIC_ERROR));
        return;
      }

      onSuccess();
    } catch {
      setError(GENERIC_ERROR);
    } finally {
      setPending(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} noValidate className="flex flex-col gap-4">
      <p className="text-sm text-neutral-600">
        We emailed you a code — enter it below. Sent to {email}.
      </p>

      <div className="flex flex-col gap-1">
        <label htmlFor="otp-code" className="text-sm font-medium text-navy-900">
          Verification code
        </label>
        <input
          id="otp-code"
          name="otp"
          type="text"
          inputMode="numeric"
          autoComplete="one-time-code"
          maxLength={6}
          required
          value={code}
          disabled={pending}
          onChange={handleCodeChange}
          className="num rounded-md border border-neutral-200 bg-neutral-0 px-3 py-2 text-navy-900 outline-none focus:border-navy-500 disabled:opacity-50"
        />
      </div>

      {error && (
        <p role="alert" className="text-sm text-status-danger">
          {error}
        </p>
      )}

      <Button type="submit" disabled={pending} isLoading={pending}>
        Verify
      </Button>

      <button
        type="button"
        disabled={pending}
        onClick={onBack}
        className="text-sm text-navy-500 underline hover:text-navy-700 disabled:cursor-not-allowed disabled:opacity-50"
      >
        Use a different email
      </button>
    </form>
  );
}
