import { AuthCard } from "@cq/ui";

import { AuthFlow } from "../../features/auth";

// `AuthCard` has no hooks of its own (see packages/ui/src/auth/AuthCard.tsx),
// so it's safe to import into this Server Component; the interactive piece
// (`AuthFlow`) is a "use client" child.
export default function LoginPage() {
  return (
    <AuthCard heading="Clear Quote — LO Console">
      <AuthFlow />
    </AuthCard>
  );
}
