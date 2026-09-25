"use client";

import { useWorkspace } from "./WorkspaceProvider";

// A non-404 failure (network blip, 500, ...) -- distinct from `NotFoundPanel`
// so a real outage doesn't read as "you don't have access".
export function ErrorPanel() {
  const { refetch } = useWorkspace();
  return (
    <div className="flex flex-col items-center gap-3 px-6 py-16 text-center">
      <h1 className="text-lg font-semibold text-navy-900">Couldn&apos;t load this application</h1>
      <p className="max-w-md text-sm text-neutral-600">
        Something went wrong loading this application. Try again.
      </p>
      <button
        type="button"
        onClick={() => refetch()}
        className="text-sm font-medium text-navy-500 hover:underline"
      >
        Retry
      </button>
    </div>
  );
}
