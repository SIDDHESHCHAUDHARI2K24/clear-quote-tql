import { HousingTab } from "../../../../../features/verification/housing/HousingTab";

export default async function HousingTabPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <HousingTab applicationId={id} />;
}
