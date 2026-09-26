"use client";

import { Pagination } from "@cq/ui";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import {
  ApplicationsFilterBar,
  ApplicationsTable,
  fetchApplications,
  fetchLoOptions,
  filtersToApiQuery,
  useApplicationFilters,
  type ApplicationListRow,
  type LoOption,
} from "../../../features/applications";
import { useStaffSession } from "../../../features/shell";

type LoadState =
  | { kind: "loading" }
  | { kind: "ready"; items: ApplicationListRow[]; total: number }
  | { kind: "error" };

// spec.md CQ-027 "Frontend": filter bar, sortable table, pagination and a
// row click into the workspace. All filters live in the URL
// (`useApplicationFilters`), so a reload, back-navigation, or a CQ-025
// dashboard tile link (`?status=sent_or_later`, `?has_property=true`, ...)
// all land on the exact same filtered/sorted/paginated table (AC6).
export default function ApplicationsPage() {
  const router = useRouter();
  const { isManagerOrAdmin } = useStaffSession();
  const { filters, setFilters, clearFilters } = useApplicationFilters();
  const [state, setState] = useState<LoadState>({ kind: "loading" });
  const [loOptions, setLoOptions] = useState<LoOption[]>([]);

  useEffect(() => {
    let cancelled = false;
    setState({ kind: "loading" });
    fetchApplications(filtersToApiQuery(filters))
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
      <h1 className="text-lg font-semibold text-navy-900">Applications</h1>

      <ApplicationsFilterBar
        filters={filters}
        onChange={setFilters}
        onClear={clearFilters}
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
          Couldn&apos;t load applications.
        </p>
      )}
      {state.kind === "ready" && (
        <>
          <ApplicationsTable
            rows={state.items}
            sort={filters.sort}
            onSortChange={(sort) => setFilters({ sort })}
            onRowClick={(row) => router.push(`/applications/${row.id}`)}
          />
          <Pagination
            page={filters.page}
            pageSize={filters.pageSize}
            total={state.total}
            onChange={(page) => setFilters({ page })}
            label="Applications pagination"
          />
        </>
      )}
    </div>
  );
}
