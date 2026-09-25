"use client";

import { applicationStatusLabel } from "../../features/auth";
import { StubPage, useBorrowerSession } from "../../features/shell";

// `/` -- borrower home. P5/P6 foundation keeps the old placeholder's
// behaviour (greeting + latest application status) inside the portal
// shell; CQ-031 replaces it with the real home/status page. Session
// checking and Sign out moved to the `(portal)` layout's
// `BorrowerSessionProvider` / `PortalShell`.
export default function HomePage() {
  const { me } = useBorrowerSession();

  return (
    <StubPage title={`Hi ${me.first_name}`} item="CQ-031">
      <p role="status" className="text-navy-900">
        {me.latest_application
          ? applicationStatusLabel(me.latest_application.status)
          : "No application yet"}
      </p>
    </StubPage>
  );
}
