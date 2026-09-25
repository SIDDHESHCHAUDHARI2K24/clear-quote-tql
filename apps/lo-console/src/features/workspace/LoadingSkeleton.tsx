// spec.md scope: "Loading skeleton, 404 page and 403 page." Shown while
// `WorkspaceProvider`'s first `GET .../summary` is in flight.
export function LoadingSkeleton() {
  return (
    <div role="status" aria-label="Loading application" className="animate-pulse px-6 py-4">
      <div className="mb-4 h-6 w-48 rounded bg-neutral-200" />
      <div className="mb-6 flex gap-8">
        {Array.from({ length: 5 }).map((_, index) => (
          <div key={index} className="flex flex-col gap-2">
            <div className="h-3 w-20 rounded bg-neutral-200" />
            <div className="h-4 w-16 rounded bg-neutral-200" />
          </div>
        ))}
      </div>
      <div className="h-64 rounded bg-neutral-100" />
    </div>
  );
}
