"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";

import { LoginForm } from "./LoginForm";
import { SignupForm } from "./SignupForm";
import { OtpForm } from "./OtpForm";

export type AuthFlowMode = "login" | "signup";

type Step = { kind: "form" } | { kind: "otp"; challengeId: string; email: string };

export interface AuthFlowProps {
  mode: AuthFlowMode;
}

// Owns the login/signup -> OTP step transition; `src/app/login/page.tsx`
// and `src/app/signup/page.tsx` just render this inside their card.
export function AuthFlow({ mode }: AuthFlowProps) {
  const router = useRouter();
  const [step, setStep] = useState<Step>({ kind: "form" });

  if (step.kind === "otp") {
    return (
      <OtpForm
        challengeId={step.challengeId}
        email={step.email}
        onBack={() => setStep({ kind: "form" })}
        onSuccess={() => router.replace("/")}
      />
    );
  }

  const onChallenge = (challengeId: string, email: string) =>
    setStep({ kind: "otp", challengeId, email });

  if (mode === "signup") {
    return (
      <div className="flex flex-col gap-4">
        <SignupForm onChallenge={onChallenge} />
        <p className="text-center text-sm text-neutral-600">
          Already have an account?{" "}
          <Link href="/login" className="text-navy-500 underline hover:text-navy-700">
            Sign in
          </Link>
        </p>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-4">
      <LoginForm onChallenge={onChallenge} />
      <p className="text-center text-sm text-neutral-600">
        New here?{" "}
        <Link href="/signup" className="text-navy-500 underline hover:text-navy-700">
          Create an account
        </Link>
      </p>
    </div>
  );
}
