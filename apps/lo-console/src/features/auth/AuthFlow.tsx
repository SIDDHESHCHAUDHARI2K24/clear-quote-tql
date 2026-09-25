"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

import { LoginForm } from "./LoginForm";
import { OtpForm } from "./OtpForm";

type Step = { kind: "login" } | { kind: "otp"; challengeId: string; email: string };

// Owns the login -> OTP step transition; `src/app/login/page.tsx` just
// renders this inside its card.
export function AuthFlow() {
  const router = useRouter();
  const [step, setStep] = useState<Step>({ kind: "login" });

  if (step.kind === "otp") {
    return (
      <OtpForm
        challengeId={step.challengeId}
        email={step.email}
        onBack={() => setStep({ kind: "login" })}
        onSuccess={() => router.replace("/")}
      />
    );
  }

  return (
    <LoginForm onChallenge={(challengeId, email) => setStep({ kind: "otp", challengeId, email })} />
  );
}
