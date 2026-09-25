"use client";

import { CredentialsForm } from "@cq/ui";

import { api } from "../../lib/api-client";

export interface LoginFormProps {
  // Called once the API has issued an OTP challenge for `email`.
  onChallenge: (challengeId: string, email: string) => void;
}

export function LoginForm({ onChallenge }: LoginFormProps) {
  return (
    <CredentialsForm
      submitLabel="Sign in"
      onSubmit={async ({ email, password }) => {
        const { data, error } = await api.POST("/api/v1/auth/borrower/login", {
          body: { email, password },
        });
        if (!data) return { ok: false, error };
        return { ok: true, data };
      }}
      onSuccess={(data, { email }) => onChallenge(data.challenge_id, email)}
    />
  );
}
