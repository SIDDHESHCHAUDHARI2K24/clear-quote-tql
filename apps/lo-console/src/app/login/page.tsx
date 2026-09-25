import { AuthFlow } from "../../features/auth";

export default function LoginPage() {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center p-8">
      <div className="w-full max-w-sm rounded-lg border border-neutral-200 bg-neutral-0 p-6 shadow-sm">
        <h1 className="mb-6 text-center text-xl font-semibold text-navy-900">
          Clear Quote — LO Console
        </h1>
        <AuthFlow />
      </div>
    </main>
  );
}
