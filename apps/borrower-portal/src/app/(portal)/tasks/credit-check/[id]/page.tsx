import { CreditConsent } from "../../../../../features/credit-consent";

interface CreditCheckTaskPageProps {
  // Next 15: dynamic route `params` is a Promise on a page component.
  params: Promise<{ id: string }>;
}

/**
 * `/tasks/credit-check/{id}` (CQ-033): the borrower authorizes or declines
 * a hard credit pull. Linked from the home task banner (CQ-031) and the
 * request email (CQ-028). `CreditConsent` fetches and renders every state.
 */
export default async function CreditCheckTaskPage({ params }: CreditCheckTaskPageProps) {
  const { id } = await params;
  return <CreditConsent consentId={id} />;
}
