"use client";

import { usePathname, useRouter } from "next/navigation";

import { Tabs } from "@cq/ui";
import type { TabItem } from "@cq/ui";

import type { ApplicationSummary, ApplicationTab } from "./api";

const TAB_LABELS: Record<ApplicationTab, string> = {
  borrowers: "Borrowers",
  housing: "Housing",
  credit: "Credit & liabilities",
  assets: "Assets & income",
  property: "Property",
  pricing: "Pricing & Quote Builder",
  send: "Send",
};

const STATE_TO_TAB_STATUS: Record<ApplicationSummary["tabs"][number]["state"], TabItem["status"]> =
  {
    ok: "complete",
    flagged: "flagged",
    pending: "pending",
  };

export interface TabRailProps {
  applicationId: string;
  tabs: ApplicationSummary["tabs"];
}

// spec.md "Tab rail": tab label + a green check (ok), a red count badge
// (flagged) or a grey dot (pending); navigates between the 7 nested routes
// under `/applications/[id]/<tab>`.
export function TabRail({ applicationId, tabs }: TabRailProps) {
  const router = useRouter();
  const pathname = usePathname();
  const activeSegment = pathname.split("/").filter(Boolean).pop() ?? "";

  const items: TabItem[] = tabs.map((tab) => ({
    id: tab.tab,
    label: TAB_LABELS[tab.tab],
    status: STATE_TO_TAB_STATUS[tab.state],
    flagCount: tab.flag_count,
  }));

  return (
    <Tabs
      items={items}
      activeId={activeSegment}
      onChange={(id) => router.push(`/applications/${applicationId}/${id}`)}
    />
  );
}
