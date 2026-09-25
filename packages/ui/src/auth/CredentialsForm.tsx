"use client";

import { useState } from "react";
import type { FormEvent } from "react";

import { Button } from "../components/Button";
import { TextField } from "./TextField";
import { useAsyncSubmit } from "./useAsyncSubmit";
import type { AsyncSubmitResult } from "./useAsyncSubmit";

const GENERIC_ERROR = "Something went wrong. Try again.";

export interface CredentialsFormValues {
  email: string;
  password: string;
}

export interface CredentialsFormProps<TData> {
  submitLabel: string;
  // The app makes the actual API call and reports back whether it
  // succeeded; this package never imports `@cq/api-client` or `next/*`.
  onSubmit: (values: CredentialsFormValues) => Promise<AsyncSubmitResult<TData>>;
  onSuccess: (data: TData, values: CredentialsFormValues) => void;
  passwordAutoComplete?: "current-password" | "new-password";
  emailAutoFocus?: boolean;
}

// Generic email + password form shared by the LO Console's staff login and
// the Borrower Portal's login. Sign-up (which also needs a full name and a
// confirm-password field) composes its own form out of `TextField` plus
// this package's `useAsyncSubmit` rather than wrapping this component.
export function CredentialsForm<TData>({
  submitLabel,
  onSubmit,
  onSuccess,
  passwordAutoComplete = "current-password",
}: CredentialsFormProps<TData>) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");

  const { pending, error, run } = useAsyncSubmit<CredentialsFormValues, TData>(onSubmit, {
    fallbackError: GENERIC_ERROR,
    onSuccess,
  });

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    void run({ email, password });
  }

  return (
    <form onSubmit={handleSubmit} noValidate className="flex flex-col gap-4">
      <TextField
        id="credentials-email"
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
        id="credentials-password"
        name="password"
        label="Password"
        type="password"
        autoComplete={passwordAutoComplete}
        required
        value={password}
        disabled={pending}
        onChange={(event) => setPassword(event.target.value)}
      />

      {error && (
        <p role="alert" className="text-sm text-status-danger">
          {error}
        </p>
      )}

      <Button type="submit" disabled={pending} isLoading={pending}>
        {submitLabel}
      </Button>
    </form>
  );
}
