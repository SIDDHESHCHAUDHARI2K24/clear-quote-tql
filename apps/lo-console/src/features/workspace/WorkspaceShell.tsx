"use client";

import type { ReactNode } from "react";

import { ErrorPanel } from "./ErrorPanel";
import { LoadingSkeleton } from "./LoadingSkeleton";
import { NotFoundPanel } from "./NotFoundPanel";
import { WorkspaceHeader } from "./WorkspaceHeader";
import { useWorkspace, WorkspaceProvider } from "./WorkspaceProvider";

function WorkspaceBody({ children }: { children: ReactNode }) {
  const { state } = useWorkspace();

  if (state.kind === "loading") return <LoadingSkeleton />;
  if (state.kind === "not-found") return <NotFoundPanel />;
  if (state.kind === "error") return <ErrorPanel />;

  return (
    <>
      <WorkspaceHeader />
      <div className="px-6 py-6">{children}</div>
    </>
  );
}

export interface WorkspaceShellProps {
  applicationId: string;
  children: ReactNode;
}

// The `/applications/[id]/**` layout's root: fetches + polls the summary
// (`WorkspaceProvider`) and renders the sticky header/tab rail around
// whichever tab route is active, or the loading/not-found/error state in
// its place.
export function WorkspaceShell({ applicationId, children }: WorkspaceShellProps) {
  return (
    <WorkspaceProvider applicationId={applicationId}>
      <WorkspaceBody>{children}</WorkspaceBody>
    </WorkspaceProvider>
  );
}
