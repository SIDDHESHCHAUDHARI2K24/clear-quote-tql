import Link from "next/link";

// plan.md decision #1 (D6): `get_scoped_application` 404s an out-of-scope
// application (Decision #11's style, kept over the spec's original "403
// page" wording) -- one page covers both "doesn't exist" and "not yours to
// see" so the response can't be used to confirm another LO's application
// id exists.
export function NotFoundPanel() {
  return (
    <div className="flex flex-col items-center gap-3 px-6 py-16 text-center">
      <h1 className="text-lg font-semibold text-navy-900">Application not found</h1>
      <p className="max-w-md text-sm text-neutral-600">
        This application doesn&apos;t exist, or you don&apos;t have access to it.
      </p>
      <Link href="/" className="text-sm font-medium text-navy-500 hover:underline">
        Back to dashboard
      </Link>
    </div>
  );
}
