"use client";

import { Suspense } from "react";
import { useRouter, useSearchParams } from "next/navigation";

import { Drawer } from "@cq/ui";

import { OutboxDetail, OutboxList } from "../../../features/outbox";
import type { OutboxEmailRow } from "../../../features/outbox";

// spec.md CQ-029 "Outbox": table + search/type filter, with a detail
// drawer. `?email_id=` deep-links here (CQ-020's future "Open in Outbox"
// link).
function OutboxPageContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const selectedId = searchParams.get("email_id");

  function open(row: OutboxEmailRow) {
    router.replace(`/outbox?email_id=${row.id}`);
  }

  function close() {
    router.replace("/outbox");
  }

  return (
    <div className="mx-auto max-w-5xl px-6 py-6">
      <h1 className="mb-4 text-lg font-semibold text-navy-900">Outbox</h1>
      <OutboxList onSelect={open} />
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
