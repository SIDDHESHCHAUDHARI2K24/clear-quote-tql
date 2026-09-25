import Link from "next/link";

import type { DashboardTiles } from "./api";
import { TILE_CONFIG, tileHref } from "./tileConfig";

export interface TilesProps {
  tiles: DashboardTiles;
  loId: string | null;
}

// spec.md: "Seven tiles in one responsive row (wraps at < 1280 px); each
// tile is a link." `Link` renders a real `<a>`, so every tile is reachable
// and activatable by keyboard with no extra work (AC7).
export function Tiles({ tiles, loId }: TilesProps) {
  return (
    // `aria-label` gives this an implicit "region" landmark role, distinct
    // from the shell's own nav links of the same name (e.g. "Clients") --
    // both e2e specs and Vitest can scope to it unambiguously.
    <section
      aria-label="Dashboard tiles"
      className="grid grid-cols-2 gap-3 sm:grid-cols-3 xl:grid-cols-7"
    >
      {TILE_CONFIG.map((tile) => (
        <Link
          key={tile.key}
          href={tileHref(tile.href, loId)}
          className="flex flex-col gap-1 rounded-lg border border-neutral-200 bg-neutral-0 p-4 shadow-sm transition-colors hover:border-navy-500 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-navy-500"
        >
          <span className="text-2xl font-semibold tabular-nums text-navy-900">
            {tiles[tile.key]}
          </span>
          <span className="text-sm text-neutral-600">{tile.label}</span>
        </Link>
      ))}
    </section>
  );
}
