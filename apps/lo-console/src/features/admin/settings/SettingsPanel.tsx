"use client";

import { useEffect, useState } from "react";

import { extractErrorMessage } from "@cq/ui";

import { fetchSettings } from "./api";
import type { SettingValue } from "./api";

const SOURCE_LABEL: Record<SettingValue["source"], string> = {
  settings_table: "Seed",
  code_default: "Config default",
};

function formatValue(value: unknown): string {
  if (typeof value === "number") return String(value);
  if (typeof value === "boolean") return value ? "true" : "false";
  if (value === null || value === undefined) return "—";
  return JSON.stringify(value);
}

type LoadState =
  | { kind: "loading" }
  | { kind: "error"; message: string }
  | { kind: "ready"; settings: SettingValue[] };

/** spec.md CQ-029 "Settings" (Admin, read-only): every pricing-config
 * value with its source (AC6). No editing in this prototype. */
export function SettingsPanel() {
  const [state, setState] = useState<LoadState>({ kind: "loading" });

  useEffect(() => {
    fetchSettings().then(({ data, error }) => {
      if (error || !data) {
        setState({
          kind: "error",
          message: extractErrorMessage(error, "Couldn't load settings. Try again."),
        });
        return;
      }
      setState({ kind: "ready", settings: data.settings });
    });
  }, []);

  if (state.kind === "loading") {
    return (
      <p role="status" className="text-sm text-neutral-600">
        Loading settings…
      </p>
    );
  }

  if (state.kind === "error") {
    return (
      <p role="alert" className="text-sm text-status-danger">
        {state.message}
      </p>
    );
  }

  return (
    <table className="w-full border-collapse text-sm">
      <thead>
        <tr className="border-b border-neutral-200 text-left text-neutral-600">
          <th scope="col" className="px-3 py-2 font-medium">
            Key
          </th>
          <th scope="col" className="px-3 py-2 font-medium">
            Value
          </th>
          <th scope="col" className="px-3 py-2 font-medium">
            Source
          </th>
          <th scope="col" className="px-3 py-2 font-medium">
            Description
          </th>
        </tr>
      </thead>
      <tbody>
        {state.settings.map((setting) => (
          <tr key={setting.key} className="border-b border-neutral-100">
            <td className="px-3 py-2 font-mono text-xs text-navy-900">{setting.key}</td>
            <td className="px-3 py-2 num text-navy-900">{formatValue(setting.value)}</td>
            <td className="px-3 py-2 text-neutral-600">{SOURCE_LABEL[setting.source]}</td>
            <td className="px-3 py-2 text-neutral-600">{setting.description ?? "—"}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
