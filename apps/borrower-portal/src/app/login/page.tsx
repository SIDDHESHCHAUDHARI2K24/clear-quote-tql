import { AuthCard } from "@cq/ui";

import { AuthFlow } from "../../features/auth";

// CQ-034 spec.md: a logged-out visitor can't call an authenticated
// endpoint to read the live `settings.support_inbox` (backend/app/core/
// config.py), so this is a build-time display value, not a fetch --
// `NEXT_PUBLIC_SUPPORT_EMAIL` (mirrors `NEXT_PUBLIC_API_URL`'s pattern in
// `lib/api-client.ts`), falling back to the same default the backend
// setting has. Code-review finding (round 1): keep the two in sync by
// setting `SUPPORT_INBOX` and `NEXT_PUBLIC_SUPPORT_EMAIL` together
// whenever either is overridden (see `.env.example` and
// `apps/borrower-portal/.env.example`).
const SUPPORT_EMAIL = process.env.NEXT_PUBLIC_SUPPORT_EMAIL ?? "support@tql.local";

interface LoginPageProps {
  // Next 15: `searchParams` is a Promise on a page component. `next`
  // (CQ-022, H2) carries a signed-out redirect (e.g. from `/report/{token}`
  // via middleware) through OTP and back out -- `AuthFlow` validates it
  // before ever navigating (see lib/nextParam.ts).
  searchParams: Promise<{ next?: string }>;
}

// `AuthCard` has no hooks of its own (see packages/ui/src/auth/AuthCard.tsx),
// so it's safe to import into this Server Component; the interactive piece
// (`AuthFlow`) is a "use client" child.
export default async function LoginPage({ searchParams }: LoginPageProps) {
  const { next } = await searchParams;
  return (
    <AuthCard heading="Clear Quote" subtitle="Sign in to see your numbers">
      <AuthFlow mode="login" next={next} />
      <p className="mt-4 text-center text-sm text-neutral-600">
        Need help signing in? Email us at{" "}
        <a href={`mailto:${SUPPORT_EMAIL}`} className="text-navy-500 underline">
          {SUPPORT_EMAIL}
        </a>
        .
      </p>
    </AuthCard>
  );
}
