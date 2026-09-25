"use client";

import { useState } from "react";
import type { ChangeEvent, FormEvent, ReactNode } from "react";

import { Button } from "../components/Button";
import { TextField } from "./TextField";
import { useAsyncSubmit } from "./useAsyncSubmit";
import type { AsyncSubmitResult } from "./useAsyncSubmit";

const GENERIC_ERROR = "Something went wrong. Try again.";
const DIGITS_ONLY = /\D/g;

export interface OtpFormValues {
  challengeId: string;
  code: string;
}

export interface OtpFormProps<TData> {
  challengeId: string;
  // Full copy above the input, e.g. "Enter the 6-digit code sent to
  // {email}." — wording (and the email interpolation) differs per app, so
  // the caller composes it rather than passing `email` through here.
  description: ReactNode;
  // "Use a different account" (LO Console) vs "Use a different email"
  // (Borrower Portal).
  backLabel: string;
  onSubmit: (values: OtpFormValues) => Promise<AsyncSubmitResult<TData>>;
  onSuccess: () => void;
  onBack: () => void;
}

// Shared by both apps' OTP-verification step (LoginForm and, on the
// Borrower Portal, SignupForm both land here via AuthFlow).
export function OtpForm<TData>({
  challengeId,
  description,
  backLabel,
  onSubmit,
  onSuccess,
  onBack,
}: OtpFormProps<TData>) {
  const [code, setCode] = useState("");

  const { pending, error, run } = useAsyncSubmit<OtpFormValues, TData>(onSubmit, {
    fallbackError: GENERIC_ERROR,
    onSuccess,
  });

  function handleCodeChange(event: ChangeEvent<HTMLInputElement>) {
    setCode(event.target.value.replace(DIGITS_ONLY, "").slice(0, 6));
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    void run({ challengeId, code });
  }

  return (
    <form onSubmit={handleSubmit} noValidate className="flex flex-col gap-4">
      <p className="text-sm text-neutral-600">{description}</p>

      <TextField
        id="otp-code"
        name="otp"
        label="Verification code"
        type="text"
        inputMode="numeric"
        autoComplete="one-time-code"
        maxLength={6}
        required
        value={code}
        disabled={pending}
        onChange={handleCodeChange}
        className="num"
      />

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
        {backLabel}
      </button>
    </form>
  );
}
