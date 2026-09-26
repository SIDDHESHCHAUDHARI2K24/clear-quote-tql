"use client";

import { Button, Overlay } from "@cq/ui";
import { useState } from "react";

import { chooseProduct, fetchProducts, type ProductRow, type ScenarioGroup } from "./api";
import { CompareTable } from "./CompareTable";
import { ManualGrid } from "./ManualGrid";
import { PricingProblemNotice } from "./PricingProblemNotice";
import { MAX_COMPARE, QuoteGroups } from "./QuoteGroups";
import { ScenarioOverlay, type OverlayMode } from "./ScenarioOverlay";
import { useQuoteBuilder } from "./useQuoteBuilder";

export interface QuoteBuilderProps {
  /** From the pricing view (CQ-017); used until this builder's own data
   * has loaded (plan.md Decision 10). */
  hasStaleQuotes: boolean;
}

type ManualState =
  | { kind: "closed" }
  | { kind: "loading"; scenarioId: string }
  | { kind: "ready"; scenarioId: string; rows: ProductRow[] };

/** The Pricing tab's bottom half: quote groups and cards, the stale
 * banner's Re-price, the Add/Edit overlay, Choose manually and Compare. */
export function QuoteBuilder({ hasStaleQuotes }: QuoteBuilderProps) {
  const builder = useQuoteBuilder();
  const { applicationId, load, busy, problem, setProblem } = builder;
  const [overlay, setOverlay] = useState<OverlayMode | null>(null);
  const [manual, setManual] = useState<ManualState>({ kind: "closed" });
  const [compareIds, setCompareIds] = useState<string[]>([]);
  const [compareOpen, setCompareOpen] = useState(false);

  const view = load.kind === "ready" ? load.view : null;
  const groups: ScenarioGroup[] = view?.groups ?? [];
  const allQuotes = groups.flatMap((g) => g.quotes);
  const hasStale = view ? allQuotes.some((q) => q.stale) : hasStaleQuotes;
  const compareSet = new Set(compareIds);
  const compareQuotes = allQuotes.filter((q) => compareSet.has(q.id));

  const toggleCompare = (quoteId: string) =>
    setCompareIds((ids) =>
      ids.includes(quoteId)
        ? ids.filter((id) => id !== quoteId)
        : ids.length >= MAX_COMPARE
          ? ids
          : [...ids, quoteId],
    );

  const handleDelete = async (quoteId: string) => {
    setCompareIds((ids) => ids.filter((id) => id !== quoteId));
    await builder.remove(quoteId);
  };

  const openManual = async (scenarioId: string) => {
    setOverlay(null);
    setManual({ kind: "loading", scenarioId });
    const result = await fetchProducts(scenarioId);
    if (!result.ok) {
      setManual({ kind: "closed" });
      setProblem(result.problem);
      await builder.reload();
      return;
    }
    setManual({ kind: "ready", scenarioId, rows: result.data });
  };

  const choose = async (row: ProductRow) => {
    if (manual.kind !== "ready") return;
    const result = await builder.run(() => chooseProduct(manual.scenarioId, row));
    if (result.ok) setManual({ kind: "closed" });
  };

  return (
    <section aria-label="Quote builder" className="flex flex-col gap-4">
      {hasStale && (
        <div
          role="status"
          className="flex items-center justify-between gap-3 rounded-md border border-status-warning bg-status-warning/10 px-4 py-3 text-sm text-navy-900"
        >
          <span>Quotes are out of date — Re-price</span>
          <Button size="sm" variant="secondary" onClick={builder.reprice} isLoading={busy}>
            Re-price
          </Button>
        </div>
      )}

      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-lg font-semibold text-navy-900">Quotes</h2>
        <div className="flex gap-2">
          <Button
            variant="secondary"
            size="sm"
            disabled={compareIds.length < 2}
            onClick={() => setCompareOpen(true)}
          >
            {`Compare (${compareIds.length})`}
          </Button>
          <Button
            size="sm"
            disabled={load.kind !== "ready" || busy}
            onClick={() => setOverlay({ kind: "add", base: groups[0] ?? null })}
          >
            Add scenario
          </Button>
        </div>
      </div>

      {problem && <PricingProblemNotice applicationId={applicationId} problem={problem} />}

      {load.kind === "loading" && (
        <div role="status" aria-label="Loading quotes" className="animate-pulse">
          <div className="h-40 rounded bg-neutral-100" />
        </div>
      )}
      {load.kind === "error" && (
        <p role="alert" className="text-sm text-status-danger">
          Couldn&apos;t load quotes.{" "}
          <button type="button" className="underline" onClick={builder.reload}>
            Try again
          </button>
        </p>
      )}
      {view && (
        <QuoteGroups
          groups={groups}
          strategy={view.strategy ?? null}
          busy={busy}
          compareIds={compareIds}
          onRecommend={builder.recommend}
          onEdit={(group) => setOverlay({ kind: "edit", group })}
          onDelete={handleDelete}
          onToggleCompare={toggleCompare}
        />
      )}

      {overlay && (
        <ScenarioOverlay
          key={overlay.kind === "edit" ? overlay.group.id : "add"}
          applicationId={applicationId}
          strategy={view?.strategy ?? null}
          mode={overlay}
          onClose={() => setOverlay(null)}
          onSaved={builder.refresh}
          onChooseManually={openManual}
        />
      )}

      <Overlay
        isOpen={manual.kind !== "closed"}
        onClose={() => setManual({ kind: "closed" })}
        size="full"
        title="Choose manually"
      >
        {manual.kind === "loading" && (
          <div
            role="status"
            aria-label="Loading products"
            className="h-40 animate-pulse rounded bg-neutral-100"
          />
        )}
        {manual.kind === "ready" && <ManualGrid rows={manual.rows} busy={busy} onChoose={choose} />}
      </Overlay>

      <Overlay
        isOpen={compareOpen && compareQuotes.length >= 2}
        onClose={() => setCompareOpen(false)}
        size="lg"
        title="Compare quotes"
      >
        <CompareTable quotes={compareQuotes} strategy={view?.strategy ?? null} />
      </Overlay>
    </section>
  );
}
