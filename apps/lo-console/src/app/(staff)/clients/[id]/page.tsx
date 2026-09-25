import { ClientDetailView } from "../../../../features/clients";

// spec.md CQ-026: Next 15 App Router hands a dynamic segment's `params` to
// a page as a Promise; this stays a (default) Server Component just to
// `await` it once and pass the plain `id` string down to the client-side
// `ClientDetailView` (mirrors `applications/[id]/layout.tsx`).
export default async function ClientDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  return <ClientDetailView clientId={id} />;
}
