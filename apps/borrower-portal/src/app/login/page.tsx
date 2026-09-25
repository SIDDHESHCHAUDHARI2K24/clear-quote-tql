import { AuthCard } from "@cq/ui";

import { AuthFlow } from "../../features/auth";

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
    </AuthCard>
  );
}
