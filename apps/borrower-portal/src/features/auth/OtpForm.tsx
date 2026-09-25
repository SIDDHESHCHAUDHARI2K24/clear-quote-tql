"use client";

import { OtpForm as SharedOtpForm } from "@cq/ui";

import { api } from "../../lib/api-client";

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
  return (
    <SharedOtpForm
      challengeId={challengeId}
      description={`We emailed you a code — enter it below. Sent to ${email}.`}
      backLabel="Use a different email"
      onSubmit={async ({ challengeId: id, code }) => {
        const { data, error } = await api.POST("/api/v1/auth/borrower/otp/verify", {
          body: { challenge_id: id, code },
        });
        if (!data) return { ok: false, error };
        return { ok: true, data };
      }}
      onSuccess={onSuccess}
      onBack={onBack}
    />
  );
}
