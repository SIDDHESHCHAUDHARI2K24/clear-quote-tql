"use client";

import { OtpForm as SharedOtpForm } from "@cq/ui";

import { api } from "../../lib/api-client";

export interface OtpFormProps {
  challengeId: string;
  email: string;
  // Called once the OTP has been verified and the session cookie is set.
  onSuccess: () => void;
  // "Use a different account" — restarts at the email/password step.
  onBack: () => void;
}

export function OtpForm({ challengeId, email, onSuccess, onBack }: OtpFormProps) {
  return (
    <SharedOtpForm
      challengeId={challengeId}
      description={`Enter the 6-digit code sent to ${email}.`}
      backLabel="Use a different account"
      onSubmit={async ({ challengeId: id, code }) => {
        const { data, error } = await api.POST("/api/v1/auth/staff/otp/verify", {
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
