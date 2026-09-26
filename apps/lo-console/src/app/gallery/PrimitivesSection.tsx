"use client";

import { useState } from "react";

import {
  Button,
  Card,
  Drawer,
  EmptyState,
  MultiSelect,
  Pagination,
  Select,
  ToastProvider,
  useToast,
} from "@cq/ui";

const STATUS_OPTIONS = [
  { value: "intake", label: "Intake" },
  { value: "needs_attention", label: "Needs attention" },
  { value: "priced", label: "Priced" },
  { value: "sent", label: "Sent" },
];

const LO_OPTIONS = [
  { value: "jordan", label: "Jordan Lee" },
  { value: "sam", label: "Sam Patel" },
];

function ToastDemo() {
  const { show } = useToast();
  return (
    <div className="flex flex-wrap gap-3">
      <Button onClick={() => show("Saved", { tone: "success" })}>Show success toast</Button>
      <Button variant="secondary" onClick={() => show("Re-verify started", { tone: "info" })}>
        Show info toast
      </Button>
    </div>
  );
}

// P5/P6 foundation (E7): gallery entries for the new `packages/ui`
// primitives, each in at least two states.
export function PrimitivesSection() {
  const [page, setPage] = useState(2);
  const [lo, setLo] = useState("");
  const [statuses, setStatuses] = useState<string[]>(["priced"]);
  const [drawerOpen, setDrawerOpen] = useState(false);

  return (
    <ToastProvider>
      <Card title="Pagination">
        <div className="flex flex-col gap-4">
          <Pagination
            label="Pagination (middle page)"
            page={page}
            pageSize={25}
            total={212}
            onChange={setPage}
          />
          <Pagination
            label="Pagination (empty)"
            page={1}
            pageSize={25}
            total={0}
            onChange={() => {}}
          />
        </div>
      </Card>

      <Card title="Select">
        <div className="grid gap-4 sm:grid-cols-2">
          <Select
            label="Loan officer (filter)"
            options={LO_OPTIONS}
            value={lo}
            onChange={setLo}
            placeholder="Any LO"
          />
          <Select
            label="Loan officer (error)"
            options={LO_OPTIONS}
            value=""
            onChange={() => {}}
            placeholder="Choose"
            error="Choose a loan officer"
          />
        </div>
      </Card>

      <Card title="MultiSelect">
        <div className="grid gap-4 sm:grid-cols-2">
          <MultiSelect
            label="Status (filter)"
            options={STATUS_OPTIONS}
            value={statuses}
            onChange={setStatuses}
          />
          <MultiSelect
            label="Status (disabled)"
            options={STATUS_OPTIONS}
            value={[]}
            onChange={() => {}}
            disabled
          />
        </div>
      </Card>

      <Card title="Drawer">
        <Button onClick={() => setDrawerOpen(true)}>Open drawer</Button>
        <Drawer
          isOpen={drawerOpen}
          onClose={() => setDrawerOpen(false)}
          title="Activity"
          footer={<Button onClick={() => setDrawerOpen(false)}>Done</Button>}
        >
          <p>Drawer body content.</p>
        </Drawer>
      </Card>

      <Card title="EmptyState">
        <div className="grid gap-4 sm:grid-cols-2">
          <EmptyState
            title="No applications match"
            body="Try clearing a filter."
            action={<Button variant="secondary">Clear filters</Button>}
          />
          <EmptyState title="Nothing here yet" headingLevel={3} />
        </div>
      </Card>

      <Card title="Toast">
        <ToastDemo />
      </Card>
    </ToastProvider>
  );
}
