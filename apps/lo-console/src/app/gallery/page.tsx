"use client";

import { useState } from "react";

import {
  APPLICATION_STATUSES,
  Button,
  Card,
  MoneyInput,
  Overlay,
  PercentInput,
  SOURCE_BADGE_SOURCES,
  SourceBadge,
  StatusPill,
  Table,
  Tabs,
} from "@cq/ui";
import type { TabItem, TableColumn } from "@cq/ui";

import { PrimitivesSection } from "./PrimitivesSection";

interface QuoteRow {
  id: string;
  product: string;
  rate: string;
}

const tableRows: QuoteRow[] = [
  { id: "1", product: "30yr Fixed", rate: "6.750" },
  { id: "2", product: "ARM 7/6", rate: "6.250" },
];

const tableColumns: TableColumn<QuoteRow>[] = [
  { key: "product", header: "Product" },
  { key: "rate", header: "Rate", align: "right", render: (row) => `${row.rate}%` },
];

const tabItems: TabItem[] = [
  { id: "borrowers", label: "Borrowers", status: "complete" },
  { id: "housing", label: "Housing", status: "flagged", flagCount: 2 },
  { id: "credit", label: "Credit", status: "pending" },
];

export default function GalleryPage() {
  const [moneyValue, setMoneyValue] = useState("342000.00");
  const [percentValue, setPercentValue] = useState("6.750");
  const [emptyMoney, setEmptyMoney] = useState("");
  const [activeTab, setActiveTab] = useState("borrowers");
  const [overlayOpen, setOverlayOpen] = useState(false);

  return (
    <main className="mx-auto flex max-w-4xl flex-col gap-8 p-8">
      <h1 className="text-2xl font-semibold text-navy-900">Component gallery</h1>

      <Card title="Button">
        <div className="flex flex-wrap items-center gap-3">
          <Button variant="primary">Primary</Button>
          <Button variant="secondary">Secondary</Button>
          <Button variant="ghost">Ghost</Button>
          <Button variant="danger">Danger</Button>
          <Button isLoading>Loading</Button>
          <Button disabled>Disabled</Button>
        </div>
      </Card>

      <Card title="MoneyInput">
        <div className="flex flex-col gap-3">
          <MoneyInput
            aria-label="Purchase price (filled)"
            value={moneyValue}
            onChange={setMoneyValue}
          />
          <MoneyInput
            aria-label="Purchase price (empty)"
            value={emptyMoney}
            onChange={setEmptyMoney}
          />
          <MoneyInput
            aria-label="Purchase price (invalid)"
            value="abc"
            invalid
            onChange={() => {}}
          />
          <MoneyInput
            aria-label="Purchase price (sourced)"
            value="342000.00"
            onChange={() => {}}
            sourceBadge={{ source: "encompass" }}
          />
        </div>
      </Card>

      <Card title="PercentInput">
        <div className="flex flex-col gap-3">
          <PercentInput
            aria-label="Note rate (filled)"
            value={percentValue}
            onChange={setPercentValue}
          />
          <PercentInput aria-label="Note rate (empty)" value="" onChange={() => {}} />
          <PercentInput aria-label="Note rate (invalid)" value="xx" invalid onChange={() => {}} />
        </div>
      </Card>

      <Card title="Table">
        <Table columns={tableColumns} rows={tableRows} rowKey={(r) => r.id} />
        <div className="mt-4">
          <Table columns={tableColumns} rows={[]} rowKey={(r) => r.id} emptyState="No quotes yet" />
        </div>
      </Card>

      <Card title="Tabs">
        <Tabs items={tabItems} activeId={activeTab} onChange={setActiveTab} />
      </Card>

      <Card title="StatusPill — every ApplicationStatus">
        <div className="flex flex-wrap gap-2">
          {APPLICATION_STATUSES.map((status) => (
            <StatusPill key={status} status={status} />
          ))}
        </div>
      </Card>

      <Card title="SourceBadge — every SourceBadgeSource">
        <div className="flex flex-wrap gap-2">
          {SOURCE_BADGE_SOURCES.map((source) => (
            <SourceBadge key={source} source={source} onRevert={() => {}} />
          ))}
        </div>
      </Card>

      <Card title="Overlay">
        <Button onClick={() => setOverlayOpen(true)}>Open overlay</Button>
        <Overlay
          isOpen={overlayOpen}
          onClose={() => setOverlayOpen(false)}
          title="Edit quote"
          footer={<Button onClick={() => setOverlayOpen(false)}>Close</Button>}
        >
          <p>Overlay body content.</p>
        </Overlay>
      </Card>

      <PrimitivesSection />
    </main>
  );
}
