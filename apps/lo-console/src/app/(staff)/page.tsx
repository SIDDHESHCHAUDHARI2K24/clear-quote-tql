import { StubPage } from "../../features/shell";

// `/` -- the LO dashboard. P5/P6 foundation stub; CQ-025 replaces it. The
// signed-in name/role (the old placeholder home's content) now lives in
// the shell's user menu.
export default function DashboardPage() {
  return <StubPage title="Dashboard" item="CQ-025" />;
}
