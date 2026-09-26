"use client";

import { useEffect, useState } from "react";

import { EmptyState, Pagination, Select, Table, extractErrorMessage } from "@cq/ui";
import type { SelectOption, TableColumn } from "@cq/ui";

import { fetchOutboxList } from "./api";
import type { OutboxEmailRow } from "./api";

const TYPE_OPTIONS: SelectOption[] = [
  { value: "otp", label: "Sign-in code" },
  { value: "borrower_action", label: "Borrower action" },
  { value: "quote_sent", label: "Quote sent" },
  { value: "other", label: "Other" },
];

const STATUS_LABEL: Record<string, string> = {
  queued: "Queued",
  sent: "Sent",
  failed: "Failed",
};

function formatSentAt(row: OutboxEmailRow): string {
  const at = row.sent_at ?? row.created_at;
  // Pinned locale (not the runtime default -- react-doctor's
  // no-locale-format-in-render): matches packages/ui/report/format.ts's
  // own convention, so server and client always render the same string.
  return new Date(at).toLocaleString("en-US", {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

export interface OutboxListProps {
  onSelect: (row: OutboxEmailRow) => void;
  /** `/outbox?application_id=` (minor 8, review round 1): scopes the list
   * to one application, e.g. CQ-020's future "Open in Outbox" link. */
  applicationId?: string;
}

type LoadState =
  | { kind: "loading" }
  | { kind: "error"; message: string }
  | { kind: "ready"; rows: OutboxEmailRow[]; page: number; pageSize: number; total: number };

/** spec.md CQ-029 "Outbox": `/outbox` table with search + a type filter
 * (AC2/AC3). */
const SEARCH_DEBOUNCE_MS = 300;

export function OutboxList({ onSelect, applicationId }: OutboxListProps) {
  // `qInput` is what the text field shows (updates every keystroke); `q`
  // is what actually drives the fetch, debounced -- code review finding:
  // without this, every keystroke fired its own full `GET /outbox` (a
  // paginated query plus a `COUNT(*)`), almost all of them thrown away.
  const [qInput, setQInput] = useState("");
  const [q, setQ] = useState("");
  const [type, setType] = useState("");
  const [page, setPage] = useState(1);
  const [state, setState] = useState<LoadState>({ kind: "loading" });

  useEffect(() => {
    const timer = setTimeout(() => {
      setPage(1);
      setQ(qInput);
    }, SEARCH_DEBOUNCE_MS);
    return () => clearTimeout(timer);
  }, [qInput]);

  useEffect(() => {
    let cancelled = false;
    setState({ kind: "loading" });
    fetchOutboxList({ q, type, applicationId, page }).then(({ data, error }) => {
      if (cancelled) return;
      if (error || !data) {
        setState({
          kind: "error",
          message: extractErrorMessage(error, "Couldn't load the outbox. Try again."),
        });
        return;
      }
      setState({
        kind: "ready",
        rows: data.items,
        page: data.page,
        pageSize: data.page_size,
        total: data.total,
      });
    });
    return () => {
      cancelled = true;
    };
  }, [q, type, applicationId, page]);

  const columns: TableColumn<OutboxEmailRow>[] = [
    { key: "to", header: "To", render: (row) => row.to_email },
    { key: "subject", header: "Subject", render: (row) => row.subject },
    {
      key: "type",
      header: "Type",
      render: (row) => TYPE_OPTIONS.find((opt) => opt.value === row.type)?.label ?? row.type,
    },
    { key: "application", header: "Application", render: (row) => row.client_name ?? "—" },
    { key: "status", header: "Status", render: (row) => STATUS_LABEL[row.status] ?? row.status },
    { key: "sent_at", header: "Sent at", render: (row) => formatSentAt(row) },
  ];

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-end gap-3">
        <label className="flex flex-col gap-1 text-sm">
          <span className="font-medium text-navy-900">Search</span>
          <input
            type="search"
            value={qInput}
            onChange={(event) => setQInput(event.target.value)}
            placeholder="Search by recipient or subject"
            className="h-10 w-64 rounded-md border border-neutral-200 px-3 outline-none focus:border-navy-500"
          />
        </label>
        <Select
          label="Type"
          placeholder="Any type"
          options={TYPE_OPTIONS}
          value={type}
          onChange={(value) => {
            setPage(1);
            setType(value);
          }}
        />
      </div>

      {state.kind === "loading" && (
        <p role="status" className="text-sm text-neutral-600">
          Loading outbox…
        </p>
      )}
      {state.kind === "error" && (
        <p role="alert" className="text-sm text-status-danger">
          {state.message}
        </p>
      )}
      {state.kind === "ready" && (
        <>
          <Table
            columns={columns}
            rows={state.rows}
            rowKey={(row) => row.id}
            onRowClick={onSelect}
            emptyState={<EmptyState title="No emails" body="No emails match your search yet." />}
          />
          {state.total > state.pageSize && (
            <Pagination
              page={state.page}
              pageSize={state.pageSize}
              total={state.total}
              onChange={setPage}
              label="Outbox pagination"
            />
          )}
        </>
      )}
    </div>
  );
}
