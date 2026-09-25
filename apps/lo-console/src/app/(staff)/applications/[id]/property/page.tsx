import { PropertyTab } from "../../../../../features/verification/property/PropertyTab";

export default async function PropertyTabPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <PropertyTab applicationId={id} />;
}
