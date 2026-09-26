import { IntegrationsPanel } from "../../../../features/admin/integrations";

// spec.md CQ-029 "Integration panel" (Admin only -- `AdminGuard` in
// `(staff)/admin/layout.tsx` gates the route; the API enforces
// `require_roles(admin)` too).
export default function IntegrationsPage() {
  return (
    <div className="mx-auto max-w-5xl px-6 py-6">
      <h1 className="mb-4 text-lg font-semibold text-navy-900">Integrations</h1>
      <IntegrationsPanel />
    </div>
  );
}
