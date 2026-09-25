import { DefaultTabRedirect } from "../../../../features/workspace";

// spec.md: the bare `/applications/[id]` route (no tab segment) redirects
// to the default tab once the summary loads.
export default function ApplicationWorkspaceIndexPage() {
  return <DefaultTabRedirect />;
}
