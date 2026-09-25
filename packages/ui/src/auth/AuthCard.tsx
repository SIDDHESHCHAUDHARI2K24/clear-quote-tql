import type { ReactNode } from "react";

export interface AuthCardProps {
  heading: ReactNode;
  subtitle?: ReactNode;
  children: ReactNode;
}

// Centered card shell for /login and /signup. No hooks — server-safe, so
// it can be imported directly into a Server Component page the way
// `Card` already is; the interactive pieces (CredentialsForm, OtpForm)
// stay in "use client" children.
export function AuthCard({ heading, subtitle, children }: AuthCardProps) {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center p-8">
      <div className="w-full max-w-sm rounded-lg border border-neutral-200 bg-neutral-0 p-6 shadow-sm">
        <h1
          className={
            subtitle
              ? "mb-1 text-center text-xl font-semibold text-navy-900"
              : "mb-6 text-center text-xl font-semibold text-navy-900"
          }
        >
          {heading}
        </h1>
        {subtitle && <p className="mb-6 text-center text-sm text-neutral-600">{subtitle}</p>}
        {children}
      </div>
    </main>
  );
}
