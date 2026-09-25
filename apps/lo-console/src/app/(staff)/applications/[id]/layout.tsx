import type { ReactNode } from "react";

import { WorkspaceShell } from "../../../../features/workspace";

// spec.md CQ-016: the shell every other LO application screen (this tab's
// route segment, rendered as `children`) lives inside. Next 15 App Router
// hands a dynamic segment's `params` to a layout as a Promise; this stays a
// (default) Server Component just to `await` it once and pass the plain
// `id` string down to the client-side `WorkspaceShell`.
export default async function ApplicationWorkspaceLayout({
  children,
  params,
}: {
  children: ReactNode;
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  return <WorkspaceShell applicationId={id}>{children}</WorkspaceShell>;
}
