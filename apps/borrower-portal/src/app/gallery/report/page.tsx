"use client";

import { MatchList, REPORT_FIXTURES, ReportPage } from "@cq/ui";

// CQ-021 spec.md: "Gallery page /_gallery/report in both apps renders every
// component with each fixture, plus expired and superseded variants." This
// app follows the existing `/gallery` convention (see plan.md Decision 5)
// instead of `/_gallery`. `ReportPage` composes every report component this
// item owns, so rendering it once per fixture exercises all of them; CQ-019
// will later render the same `ReportPage` inside the real Send-tab preview.
// CQ-023: "use client" is required now that this page passes a
// `renderMatches` function prop across the server/client boundary into
// `ReportPage` (a Client Component) -- Next.js can't serialize a function
// from a Server Component. `apps/borrower-portal/src/features/report/
// ReportView.tsx` (the real report page) is already a Client Component for
// the same reason.
export default function ReportGalleryPage() {
  return (
    <main className="mx-auto flex max-w-4xl flex-col gap-16 p-8">
      <h1 className="text-2xl font-semibold text-navy-900">Report component gallery</h1>
      {REPORT_FIXTURES.map((fixture) => (
        <section key={fixture.key} className="flex flex-col gap-4">
          <h2 className="border-b border-neutral-200 pb-2 text-lg font-semibold text-navy-700">
            {fixture.title}
          </h2>
          <ReportPage
            viewModel={fixture.viewModel}
            renderMatches={(vm) => <MatchList matches={vm.matches} />}
          />
        </section>
      ))}
    </main>
  );
}
