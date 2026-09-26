"use client";

import { useState } from "react";

import { MatchList, ReportPage, Tabs } from "@cq/ui";

import type { Loaded, ReportViewModel } from "./api";

const TABS = [
  { id: "report", label: "Borrower report" },
  { id: "letter", label: "Pre-approval letter" },
];

export interface PreviewPanelProps {
  report: Loaded<ReportViewModel> | null;
  letter: Loaded<string> | null;
}

function Pending({ state }: { state: Loaded<unknown> | null }) {
  if (state === null) return <p className="text-sm text-neutral-600">Loading preview…</p>;
  return state.ok ? null : <p className="text-sm text-neutral-600">{state.message}</p>;
}

/** The letter in a script-less sandbox (AC7): no `allow-scripts`, no
 * `allow-same-origin`. Page width is US Letter (8.5in). */
export function LetterFrame({ html }: { html: string }) {
  return (
    <iframe
      title="Pre-approval letter preview"
      data-testid="letter-frame"
      sandbox=""
      srcDoc={html}
      className="h-[11in] w-[8.5in] max-w-full rounded-md border border-neutral-200 bg-neutral-0"
    />
  );
}

/** Exactly what the borrower will see: the same `ReportPage` (and
 * `MatchList`) the portal renders, and the letter HTML CQ-020 turns into
 * the PDF. */
export function PreviewPanel({ report, letter }: PreviewPanelProps) {
  const [tab, setTab] = useState("report");
  return (
    <section className="flex min-w-0 flex-col gap-4" aria-label="Preview">
      <Tabs items={TABS} activeId={tab} onChange={setTab} />
      {tab === "report" ? (
        <div data-testid="report-preview" className="rounded-md border border-neutral-200 p-4">
          {report?.ok ? (
            <ReportPage
              viewModel={report.data}
              renderMatches={(viewModel) => <MatchList matches={viewModel.matches} />}
            />
          ) : (
            <Pending state={report} />
          )}
        </div>
      ) : (
        <div data-testid="letter-preview" className="overflow-x-auto">
          {letter?.ok ? <LetterFrame html={letter.data} /> : <Pending state={letter} />}
        </div>
      )}
    </section>
  );
}
