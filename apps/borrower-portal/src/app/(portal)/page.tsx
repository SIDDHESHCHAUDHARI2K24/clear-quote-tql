"use client";

import { HomeView } from "../../features/home";

// `/` -- borrower home (CQ-031 spec.md). `HomeView` does the actual
// `GET /api/v1/portal/me` fetch and renders the loading/error/loaded
// states, same convention as `features/report/ReportView.tsx`.
export default function HomePage() {
  return <HomeView />;
}
