"use client";

import { Pagination } from "@cq/ui";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { fetchLoOptions, type LoOption } from "../../../features/applications";
import {
  ClientsFilterBar,
  ClientsTable,
  fetchClients,
  filtersToApiQuery,
  useClientFilters,
  type ClientRow,
} from "../../../features/clients";
import { useStaffSession } from "../../../features/shell";

type LoadState =
  | { kind: "loading" }
  | { kind: "ready"; items: ClientRow[]; total: number }
  | { kind: "error" };

// spec.md CQ-026 "Frontend": search box (debounced), filters, sortable
// table, pagination. Filters and page live in the URL
// (`useClientFilters`), so a reload or back-navigation restores the exact
// same filtered/sorted/paginated table (AC6).
const SEARCH_DEBOUNCE_MS = 300;

export default function ClientsPage() {
  const router = useRouter();
  const { isManagerOrAdmin } = useStaffSession();
  const { filters, setFilters, clearFilters } = useClientFilters();
  const [qInput, setQInput] = useState(filters.q);
  const [state, setState] = useState<LoadState>({ kind: "loading" });
  const [loOptions, setLoOptions] = useState<LoOption[]>([]);

  // The URL's `q` is the source of truth; keep the input in sync when it
  // changes from outside (a clear, a back-navigation, a dashboard link).
  useEffect(() => {
    setQInput(filters.q);
  }, [filters.q]);

  useEffect(() => {
    if (qInput === filters.q) return;
    const timer = setTimeout(() => {
      setFilters({ q: qInput });
    }, SEARCH_DEBOUNCE_MS);
    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [qInput]);

  useEffect(() => {
    let cancelled = false;
    setState({ kind: "loading" });
    fetchClients(filtersToApiQuery(filters))
      .then(({ data, error }) => {
        if (cancelled) return;
        if (data) {
          setState({ kind: "ready", items: data.items, total: data.total });
        } else {
          setState({ kind: "error" });
        }
        void error;
      })
      .catch(() => {
        if (!cancelled) setState({ kind: "error" });
      });
    return () => {
      cancelled = true;
    };
    // `filters` is a new object each render (derived from the URL); it's
    // the intended trigger for a refetch, so it's the sole dependency.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [JSON.stringify(filters)]);

  useEffect(() => {
    if (!isManagerOrAdmin) return;
    let cancelled = false;
    fetchLoOptions()
      .then(({ data }) => {
        if (!cancelled && data) setLoOptions(data);
      })
      .catch(() => {
        // The LO filter simply shows no options; every other filter still
        // works.
      });
    return () => {
      cancelled = true;
    };
  }, [isManagerOrAdmin]);

  return (
    <div className="flex flex-col gap-4 p-6">
      <h1 className="text-lg font-semibold text-navy-900">Clients</h1>

      <ClientsFilterBar
        filters={{ ...filters, q: qInput }}
        onChange={(patch) => {
          if ("q" in patch) {
            setQInput(patch.q ?? "");
            return;
          }
          setFilters(patch);
        }}
        onClear={() => {
          setQInput("");
          clearFilters();
        }}
        showLoFilter={isManagerOrAdmin}
        loOptions={loOptions}
      />

      {state.kind === "loading" && (
        <p role="status" className="text-neutral-600">
          Loading…
        </p>
      )}
      {state.kind === "error" && (
        <p role="alert" className="text-status-danger">
          Couldn&apos;t load clients.
        </p>
      )}
      {state.kind === "ready" && (
        <>
          <ClientsTable
            rows={state.items}
            sort={filters.sort}
            onSortChange={(sort) => setFilters({ sort })}
            onRowClick={(row) => router.push(`/clients/${row.id}`)}
          />
          <Pagination
            page={filters.page}
            pageSize={filters.pageSize}
            total={state.total}
            onChange={(page) => setFilters({ page })}
            label="Clients pagination"
          />
        </>
      )}
    </div>
  );
}
