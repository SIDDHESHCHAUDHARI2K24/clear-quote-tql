"use client";

import { Suspense } from "react";
import { useRouter, useSearchParams } from "next/navigation";

import { Drawer } from "@cq/ui";

import { OutboxDetail, OutboxList } from "../../../features/outbox";
import type { OutboxEmailRow } from "../../../features/outbox";

// spec.md CQ-029 "Outbox": table + search/type filter, with a detail
// drawer. `?email_id=` deep-links here (CQ-020's future "Open in Outbox"
// link); `?application_id=` scopes the list to one application (minor 8,
// review round 1).
function OutboxPageContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const selectedId = searchParams.get("email_id");
  const applicationId = searchParams.get("application_id") ?? undefined;

  function open(row: OutboxEmailRow) {
    const params = new URLSearchParams(applicationId ? { application_id: applicationId } : {});
    params.set("email_id", row.id);
    router.replace(`/outbox?${params.toString()}`);
  }

  function close() {
    const params = new URLSearchParams(applicationId ? { application_id: applicationId } : {});
    router.replace(params.toString() ? `/outbox?${params.toString()}` : "/outbox");
  }

  return (
    <div className="mx-auto max-w-5xl px-6 py-6">
      <h1 className="mb-4 text-lg font-semibold text-navy-900">Outbox</h1>
      <OutboxList onSelect={open} applicationId={applicationId} />
      <Drawer isOpen={Boolean(selectedId)} onClose={close} title="Email" size="lg">
        {selectedId && <OutboxDetail emailId={selectedId} />}
      </Drawer>
    </div>
  );
}

export default function OutboxPage() {
  return (
    <Suspense fallback={null}>
      <OutboxPageContent />
    </Suspense>
  );
}
