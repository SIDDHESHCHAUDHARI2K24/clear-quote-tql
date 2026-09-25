"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";

import { resolveNextPath } from "../../lib/nextParam";

import { LoginForm } from "./LoginForm";
import { SignupForm } from "./SignupForm";
import { OtpForm } from "./OtpForm";

export type AuthFlowMode = "login" | "signup";

type Step = { kind: "form" } | { kind: "otp"; challengeId: string; email: string };

export interface AuthFlowProps {
  mode: AuthFlowMode;
  // `?next=` from the URL (CQ-022, H2): where OTP success returns to,
  // validated by `resolveNextPath` (only a same-origin relative path is
  // ever navigated to -- see lib/nextParam.ts). Also carried through the
  // login <-> signup link so switching forms doesn't lose it.
  next?: string | null;
  // Prefills the signup form's email field (H2: "allowing an email
  // prefill") -- read from `?email=` by `src/app/signup/page.tsx`.
  defaultEmail?: string;
}

function otherModeHref(mode: AuthFlowMode, next: string | null | undefined): string {
  const path = mode === "signup" ? "/login" : "/signup";
  return next ? `${path}?next=${encodeURIComponent(next)}` : path;
}

// Owns the login/signup -> OTP step transition; `src/app/login/page.tsx`
// and `src/app/signup/page.tsx` just render this inside their card.
export function AuthFlow({ mode, next, defaultEmail }: AuthFlowProps) {
  const router = useRouter();
  const [step, setStep] = useState<Step>({ kind: "form" });

  if (step.kind === "otp") {
    return (
      <OtpForm
        challengeId={step.challengeId}
        email={step.email}
        onBack={() => setStep({ kind: "form" })}
        onSuccess={() => router.replace(resolveNextPath(next))}
      />
    );
  }

  const onChallenge = (challengeId: string, email: string) =>
    setStep({ kind: "otp", challengeId, email });

  if (mode === "signup") {
    return (
      <div className="flex flex-col gap-4">
        <SignupForm onChallenge={onChallenge} defaultEmail={defaultEmail} />
        <p className="text-center text-sm text-neutral-600">
          Already have an account?{" "}
          <Link
            href={otherModeHref(mode, next)}
            className="text-navy-500 underline hover:text-navy-700"
          >
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
        <Link
          href={otherModeHref(mode, next)}
          className="text-navy-500 underline hover:text-navy-700"
        >
          Create an account
        </Link>
      </p>
    </div>
  );
}
