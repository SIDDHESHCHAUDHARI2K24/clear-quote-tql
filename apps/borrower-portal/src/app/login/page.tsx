import { AuthFlow } from "../../features/auth";

// Plain markup rather than `@cq/ui`'s `Card`: this page is a Server
// Component, and `@cq/ui`'s components (e.g. `Overlay`) use hooks without
// their own "use client" directive, so importing the package here would
// break the server build. `@cq/ui` is used inside the "use client" forms
// instead (see features/auth/*).
export default function LoginPage() {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center p-8">
      <div className="w-full max-w-sm rounded-lg border border-neutral-200 bg-neutral-0 p-6 shadow-sm">
        <h1 className="mb-1 text-center text-xl font-semibold text-navy-900">Clear Quote</h1>
        <p className="mb-6 text-center text-sm text-neutral-600">Sign in to see your numbers</p>
        <AuthFlow mode="login" />
      </div>
    </main>
  );
}
