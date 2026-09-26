import { AssetsTab } from "../../../../../features/verification/assets/AssetsTab";

export default async function AssetsTabPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <AssetsTab applicationId={id} />;
}
