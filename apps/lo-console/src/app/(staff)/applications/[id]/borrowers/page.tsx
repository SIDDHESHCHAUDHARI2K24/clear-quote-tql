import { BorrowersTab } from "../../../../../features/verification/borrowers/BorrowersTab";

export default async function BorrowersTabPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <BorrowersTab applicationId={id} />;
}
