"use client";

import { EmptyState, extractErrorMessage } from "@cq/ui";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { ActivityTimeline } from "../../activity";
import { ApplicationRow } from "../../applications";
import type { ClientDetail } from "../types";
import { fetchClient } from "../api";
import { ClientDetailHeader } from "./ClientDetailHeader";
import { SentVersionsTable } from "./SentVersionsTable";

export interface ClientDetailViewProps {
  clientId: string;
}

type LoadState =
  | { kind: "loading" }
  | { kind: "error"; message: string }
  | { kind: "ready"; client: ClientDetail };

// spec.md CQ-026 "Frontend": header, "Applications" (the shared
// `ApplicationRow`, E9), "Quotes sent" and "Activity" (the shared
// `ActivityTimeline`, plan.md Decision 8) sections, with empty states.
export function ClientDetailView({ clientId }: ClientDetailViewProps) {
  const router = useRouter();
  const [state, setState] = useState<LoadState>({ kind: "loading" });

  useEffect(() => {
    let cancelled = false;
    setState({ kind: "loading" });
    fetchClient(clientId).then(({ data, error }) => {
      if (cancelled) return;
      if (error || !data) {
        setState({
          kind: "error",
          message: extractErrorMessage(error, "Couldn't load this client. Try again."),
        });
        return;
      }
      setState({ kind: "ready", client: data });
    });
    return () => {
      cancelled = true;
    };
  }, [clientId]);

  if (state.kind === "loading") {
    return (
      <p role="status" className="p-6 text-neutral-600">
        Loading…
      </p>
    );
  }

  if (state.kind === "error") {
    return (
      <p role="alert" className="p-6 text-status-danger">
        {state.message}
      </p>
    );
  }

  const { client } = state;

  return (
    <div className="flex flex-col gap-6 p-6">
      <ClientDetailHeader client={client} />

      <section className="flex flex-col gap-2">
        <h2 className="text-base font-semibold text-navy-900">Applications</h2>
        {client.applications.length === 0 ? (
          <EmptyState
            title="No applications yet"
            body="This client has no applications on file."
          />
        ) : (
          <table className="w-full border-collapse text-sm">
            <thead>
              <tr className="border-b border-neutral-200 text-left text-neutral-600">
                <th scope="col" className="px-3 py-2 font-medium">
                  Client
                </th>
                <th scope="col" className="px-3 py-2 font-medium">
                  Property
                </th>
                <th scope="col" className="px-3 py-2 font-medium">
                  Strategy
                </th>
                <th scope="col" className="px-3 py-2 text-right font-medium">
                  Purchase price
                </th>
                <th scope="col" className="px-3 py-2 font-medium">
                  Status
                </th>
                <th scope="col" className="px-3 py-2 text-center font-medium">
                  Flags
                </th>
                <th scope="col" className="px-3 py-2 font-medium">
                  LO
                </th>
                <th scope="col" className="px-3 py-2 font-medium">
                  Updated
                </th>
              </tr>
            </thead>
            <tbody>
              {client.applications.map((row) => (
                <ApplicationRow
                  key={row.id}
                  row={row}
                  onClick={(r) => router.push(`/applications/${r.id}`)}
                />
              ))}
            </tbody>
          </table>
        )}
      </section>

      <section className="flex flex-col gap-2">
        <h2 className="text-base font-semibold text-navy-900">Quotes sent</h2>
        <SentVersionsTable versions={client.sent_versions} />
      </section>

      <section className="flex flex-col gap-2">
        <h2 className="text-base font-semibold text-navy-900">Activity</h2>
        <ActivityTimeline events={client.activity} />
      </section>
    </div>
  );
}
