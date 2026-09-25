"use client";

import { useRouter } from "next/navigation";

import { Button } from "@cq/ui";

import type { SubmitResponse } from "./api";

/** Post-submit screen (spec.md: "After submit: confirmation screen, then
 * home (CQ-031) shows the application in 'Application received'."). Home
 * itself derives that label from the application's own status -- nothing
 * here re-derives it (AGENTS.md: money/status math stays where it's
 * computed). */
export function Confirmation({ result }: { result: SubmitResponse }) {
  const router = useRouter();

  return (
    <div role="status" className="flex flex-col gap-4">
      <h1 className="text-2xl font-semibold text-navy-900">Application submitted</h1>
      <p className="text-neutral-600">
        Thanks for applying. <strong>{result.assigned_lo_name}</strong> is your loan officer and
        will be in touch soon.
      </p>
      {!result.pipeline_started && (
        <p className="text-sm text-neutral-600">
          We&rsquo;re still finishing setup on our end -- your loan officer can restart processing
          if it doesn&rsquo;t show up shortly.
        </p>
      )}
      <Button onClick={() => router.push("/")}>Go to your home</Button>
    </div>
  );
}
