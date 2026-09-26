import { CreditTab } from "../../../../../features/verification/credit/CreditTab";

export default async function CreditTabPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <CreditTab applicationId={id} />;
}
