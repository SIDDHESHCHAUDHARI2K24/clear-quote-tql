import Link from "next/link";

import type { PortalConsent } from "./api";

function formatDate(value: string | null | undefined): string {
  if (!value) return "";
  return new Date(value).toLocaleDateString("en-US", {
    month: "long",
    day: "numeric",
    year: "numeric",
  });
}

function LoContact({ lo }: { lo: PortalConsent["lo"] }) {
  if (!lo) return null;
  return (
    <p className="text-sm text-neutral-600">
      Questions? Contact {lo.name} at{" "}
      <a className="text-navy-700 underline" href={`mailto:${lo.email}`}>
        {lo.email}
      </a>
      {lo.phone ? ` or ${lo.phone}` : ""}.
    </p>
  );
}

function HomeLink() {
  return (
    <Link href="/" className="text-sm font-medium text-navy-700 underline">
      Back to home
    </Link>
  );
}

const OUTCOME_COPY: Record<string, { title: string; body: (c: PortalConsent) => string }> = {
  accepted: {
    title: "Credit check authorized",
    body: (c) =>
      `You authorized the credit check on ${formatDate(c.decided_at)}. It is complete and your loan officer has been notified.`,
  },
  declined: {
    title: "Credit check declined",
    body: (c) =>
      `You declined the credit check on ${formatDate(c.decided_at)}. No credit check was made, and your loan officer has been notified.`,
  },
  expired: {
    title: "This request has expired",
    body: () =>
      "Credit-check requests are open for 14 days. Ask your loan officer to send a new one if you still want to go ahead.",
  },
};

/** The page once the request is no longer pending: authorized, declined or
 * expired. `role="status"` so a screen reader announces the switch from the
 * form to the confirmation. */
export function ConsentOutcome({ consent }: { consent: PortalConsent }) {
  const copy = OUTCOME_COPY[consent.status] ?? OUTCOME_COPY.expired;
  return (
    <section className="flex flex-col gap-3" role="status" aria-live="polite">
      <h1 className="text-2xl font-semibold text-navy-900">{copy.title}</h1>
      <p className="text-navy-900">{copy.body(consent)}</p>
      <LoContact lo={consent.lo} />
      <HomeLink />
    </section>
  );
}

export function ConsentNotFound() {
  return (
    <section className="flex flex-col gap-3">
      <h1 className="text-2xl font-semibold text-navy-900">Request not found</h1>
      <p className="text-navy-900">
        We couldn&rsquo;t find this credit-check request. The link may be wrong, or it may belong to
        a different account.
      </p>
      <HomeLink />
    </section>
  );
}

export function ConsentLoadError({ onRetry }: { onRetry: () => void }) {
  return (
    <section className="flex flex-col gap-3" role="alert">
      <h1 className="text-2xl font-semibold text-navy-900">Something went wrong</h1>
      <p className="text-navy-900">We couldn&rsquo;t load this request.</p>
      <button
        type="button"
        onClick={onRetry}
        className="self-start text-sm font-medium text-navy-700 underline"
      >
        Try again
      </button>
    </section>
  );
}
