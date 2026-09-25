import { AuthCard } from "@cq/ui";

import { AuthFlow } from "../../features/auth";

interface SignupPageProps {
  // Next 15: `searchParams` is a Promise on a page component. `next`
  // carries a signed-out redirect through to OTP success (CQ-022, H2);
  // `email` prefills the form when the login page's "Create an account"
  // link carried one through.
  searchParams: Promise<{ next?: string; email?: string }>;
}

// `AuthCard` has no hooks of its own (see packages/ui/src/auth/AuthCard.tsx),
// so it's safe to import into this Server Component; the interactive piece
// (`AuthFlow`) is a "use client" child.
export default async function SignupPage({ searchParams }: SignupPageProps) {
  const { next, email } = await searchParams;
  return (
    <AuthCard heading="Clear Quote" subtitle="Create your account">
      <AuthFlow mode="signup" next={next} defaultEmail={email} />
    </AuthCard>
  );
}
