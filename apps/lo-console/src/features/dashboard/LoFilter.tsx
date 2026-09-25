"use client";

import { Select } from "@cq/ui";

import type { LoOption } from "./api";

export interface LoFilterProps {
  los: LoOption[];
  value: string | null;
  onChange: (loId: string | null) => void;
}

// spec.md: "Manager/Admin: an LO filter (select) above the tiles; the
// choice stays in the URL." The URL round-trip itself lives in
// `DashboardPage` (`value`/`onChange` are controlled from there).
export function LoFilter({ los, value, onChange }: LoFilterProps) {
  return (
    <div className="max-w-xs">
      <Select
        label="Loan officer"
        value={value ?? ""}
        onChange={(next) => onChange(next === "" ? null : next)}
        placeholder="All loan officers"
        options={los.map((lo) => ({ value: lo.id, label: lo.full_name }))}
      />
    </div>
  );
}
