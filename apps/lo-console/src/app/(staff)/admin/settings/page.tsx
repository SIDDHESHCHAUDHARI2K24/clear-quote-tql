import { SettingsPanel } from "../../../../features/admin/settings";

// spec.md CQ-029 "Settings" (Admin, read-only).
export default function SettingsPage() {
  return (
    <div className="mx-auto max-w-5xl px-6 py-6">
      <h1 className="mb-4 text-lg font-semibold text-navy-900">Settings</h1>
      <SettingsPanel />
    </div>
  );
}
