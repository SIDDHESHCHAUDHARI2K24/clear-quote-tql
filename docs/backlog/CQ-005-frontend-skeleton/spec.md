# CQ-005 Frontend skeleton & design system

| Field | Value |
| --- | --- |
| Phase | P0 Foundations |
| Depends on | CQ-002 |
| Kaneo task | CQ-005 in Kaneo (task id `exsm8n0y81sz4014qlz3xrwr`) |
| Branch | `cq-005-frontend-skeleton` |
| Status | Ready — filled from design docs on 2026-09-24 |

## Goal

Both Next.js apps boot, share one design-token and component library, and can each render a page that proves the pipe to the backend works. Every later screen (CQ-016+) is built from the components this item ships, so their props are contracts, not suggestions.

## Scope

1. **Apps.** `apps/lo-console` and `apps/borrower-portal`: Next.js 15, App Router, TypeScript `strict: true`. Dev ports `3010` (lo-console) and `3020` (borrower-portal) — chosen because `lsof -iTCP -sTCP:LISTEN -P` on this machine already had `3000`, `5000`, `5200`, `7000` and `5183` (Kaneo) bound, and `9000`/`9001` are used by an unrelated local MinIO container. Port `8000` is free but is reserved for the backend API dev server (CQ-004 owns it), not a frontend port.
2. **Styling.** Tailwind v4 (CSS-first `@theme`, no `tailwind.config.js`), tokens defined once as CSS variables in `packages/ui/src/styles/tokens.css` and imported by both apps' root `globals.css` via `@import "@cq/ui/styles/tokens.css";` then `@import "tailwindcss";`.
3. **Tokens.** Navy, sage, neutral and status color scales; type scale; tabular-numeral convention (below).
4. **Components** in `packages/ui/src/components/`: Button, MoneyInput, PercentInput, Table, Tabs, StatusPill, SourceBadge, Card, Overlay. Exported from `packages/ui/src/index.ts` as `@cq/ui`.
5. **Gallery.** `/gallery` route in both apps rendering every component with fixture data (no backend call).
6. **Placeholder home page** (`/`) in both apps calling the backend `/health` endpoint through the generated api-client.
7. **api-client generation.** `openapi-typescript` + `openapi-fetch` in `packages/api-client` (`@cq/api-client`), wired to `make api-client`.
8. **Tests.** Vitest + Testing Library for every component and the two pages; react-doctor clean.

## Out of scope

- Workspace/tooling plumbing (pnpm workspace itself, root ESLint/Prettier/ruff configs, `.env.example`, Makefile skeleton) — CQ-002.
- The backend, its OpenAPI export script and the `/health` payload shape — CQ-004. This item only consumes whatever OpenAPI file CQ-004 writes.
- CI wiring of `pnpm lint`/`pnpm test` — CQ-006.
- Any auth UI (login, OTP) — CQ-014, CQ-015.
- Real application screens (workspace shell, pricing panel, dashboard, etc.) — CQ-016 onward.
- Report-specific components (hero numbers, breakdown tables, cashflow/cost-seg tables, PDF/print stylesheet) — CQ-021. This item ships only the generic primitives listed above.
- Backend/DB enum names for status and field-source (`FieldSource`, `application_status`, etc.) — CQ-007. This item defines the frontend display union only; CQ-007 should use the same string values so the api-client types line up without a mapping layer.

## References

- `docs/design/system-design.md` — "Automation-first input model" (source badges: Encompass, AirDNA, SmartAsset, Default, LO override), "Application status machine" (the 12-value enum and its mermaid diagram), "Emulated integrations" table (adds RentCast, Steadily as adapter/source names), "Architecture" → "Stack decisions" (API client generated from OpenAPI into `packages/api-client`; `packages/ui` holds tokens + shared components) and "Repo layout".
- `docs/design/data-field-catalog.md` — confirms `Encompass` as source-of-truth naming used throughout; no token/color data here (visual design is not catalogued).
- `AGENTS.md` — project map (`apps/`, `packages/ui/`, `packages/api-client/`) and commands table (`make api-client`, `make lint`, `make test`).
- `docs/roadmap.md` — CQ-005 exit check and P0 milestone ("both apps show a placeholder page calling the API").

## Acceptance criteria

Each criterion is testable and gets evidence in `post-dev.md`.

- [ ] AC1 — Roadmap exit check: a component gallery page renders in both apps; react-doctor passes.
- [ ] AC2 — `pnpm --filter lo-console dev` serves on `http://localhost:3010`; `pnpm --filter borrower-portal dev` serves on `http://localhost:3020`; both apps' `tsconfig.json` has `"strict": true` and `tsc --noEmit` is clean.
- [ ] AC3 — `packages/ui/src/styles/tokens.css` defines the navy, sage, neutral, status and type-scale variables in the "Design tokens" section below with those exact names; both apps' Tailwind build resolves classes built from them (e.g. `bg-navy-500`, `text-status-danger`).
- [ ] AC4 — Button, MoneyInput, PercentInput, Table, Tabs, StatusPill, SourceBadge, Card and Overlay exist in `packages/ui/src/components/` with the prop signatures pinned below and are exported from `@cq/ui`.
- [ ] AC5 — MoneyInput and PercentInput never parse their `value` to a number for computation: a unit test asserts `onChange` is called with the same decimal-string shape typed (e.g. typing `1234.5` emits `"1234.5"`, not `1234.5` or a reformatted `"1,234.50"`).
- [ ] AC6 — StatusPill renders the correct tone (below) for all 12 `ApplicationStatus` values; SourceBadge renders all 12 `SourceBadgeSource` values, and shows a revert affordance only for `lo_override`.
- [ ] AC7 — `/gallery` in both apps renders every component from AC4 with at least two fixture states each (e.g. MoneyInput empty/filled/invalid, every StatusPill value, every SourceBadge value).
- [ ] AC8 — `/` in both apps calls `GET /health` via `@cq/api-client` on load and renders "API reachable" or "API unreachable" without throwing, whether or not the backend is running.
- [ ] AC9 — `make api-client` runs `uv run python backend/scripts/export_openapi.py` (CQ-004's script, writes `packages/api-client/openapi.json`) then `pnpm --filter @cq/api-client generate` (`openapi-typescript`), and the regenerated `packages/api-client/src/schema.d.ts` carries a `// GENERATED FILE` banner and is not hand-edited.
- [ ] AC10 — `pnpm -r test` runs Vitest + Testing Library for `packages/ui` and both apps and is green.
- [ ] AC11 — `npx react-doctor -y --blocking error` from the repo root reports no error-level findings for `apps/lo-console`, `apps/borrower-portal` or `packages/ui`.

## Test plan

| Criterion | Test type | Test name / command |
| --- | --- | --- |
| AC1, AC7 | Manual + Vitest render test | `pnpm --filter lo-console test src/app/gallery/page.test.tsx`; same for borrower-portal |
| AC2 | Command | `pnpm --filter lo-console dev` / `pnpm --filter borrower-portal dev`; `pnpm -r exec tsc --noEmit` |
| AC3 | Command + visual | `grep -n "\-\-color-navy-500\|\-\-color-sage-500\|\-\-status-danger" packages/ui/src/styles/tokens.css`; gallery screenshot |
| AC4 | Unit (Vitest + Testing Library) | `packages/ui/src/components/**/*.test.tsx` — one render test per component |
| AC5 | Unit | `packages/ui/src/components/MoneyInput/MoneyInput.test.tsx::"emits raw decimal string"`, `PercentInput.test.tsx::"emits raw decimal string"` |
| AC6 | Unit | `StatusPill.test.tsx::"renders every ApplicationStatus"`, `SourceBadge.test.tsx::"renders every source, revert only on lo_override"` |
| AC7 | Component/integration | `gallery/page.test.tsx::"renders every component with fixtures"` (both apps) |
| AC8 | Integration (mocked fetch) | `page.test.tsx::"shows API reachable/unreachable"` using a mocked `@cq/api-client` in both apps |
| AC9 | Command | `make api-client` then `git diff --stat packages/api-client/src/schema.d.ts`; `head -1 packages/api-client/src/schema.d.ts` |
| AC10 | Command | `pnpm -r test` |
| AC11 | Command | `npx react-doctor -y --blocking error` |

## Design tokens

CSS variables in `packages/ui/src/styles/tokens.css`, defined inside a Tailwind v4 `@theme` block so utilities (`bg-navy-500`, `text-sage-700`, `text-status-danger`, …) are generated automatically.

| Scale | Steps (name → hex) |
| --- | --- |
| `--color-navy-*` | 50 `#EEF2F8`, 100 `#D9E2EF`, 300 `#90A8C7`, 500 `#3D5A80` (base/brand), 700 `#24405C`, 900 `#142033` |
| `--color-sage-*` | 50 `#F1F5EE`, 100 `#DFE9D6`, 300 `#AEC79A`, 500 `#7C9A6B` (base/accent), 700 `#5A7550`, 900 `#34452E` |
| `--color-neutral-*` | 0 `#FFFFFF`, 50 `#F7F8FA`, 100 `#EEF0F3`, 200 `#DEE1E6`, 400 `#9AA1AC`, 600 `#5C636F`, 800 `#2B2F36`, 950 `#14161A` |
| `--status-success` | `#2E7D46` |
| `--status-warning` | `#B8860B` |
| `--status-danger` | `#C1392B` |
| `--status-info` | `#2A6F97` |
| `--status-neutral` | `--color-neutral-400` |

Type scale (`--font-size-*` / line-height): `xs` 0.75rem/1rem, `sm` 0.875rem/1.25rem, `base` 1rem/1.5rem, `md` 1.125rem/1.75rem, `lg` 1.25rem/1.75rem, `xl` 1.5rem/2rem, `2xl` 1.875rem/2.25rem, `3xl` 2.25rem/2.5rem (hero numbers, used by CQ-021). Base font `--font-sans: "Inter", ui-sans-serif, system-ui, sans-serif`.

**Mono numerals.** Every rendered money/percent/rate value uses tabular figures so digits align in columns (Table numeric columns, MoneyInput/PercentInput display text, hero numbers). Use Tailwind v4's built-in `tabular-nums` utility class; `packages/ui/src/styles/tokens.css` also defines a `.num` utility (`font-variant-numeric: tabular-nums; font-feature-settings: "tnum" 1;`) for the eventual print stylesheet (CQ-021), which does not go through Tailwind's JIT.

## Component contracts

`MoneyInput`/`PercentInput` are display/input only: they hold and emit decimal strings, never numbers, and perform no arithmetic — money math lives only in `quote_engine` per `AGENTS.md`.

```ts
// Button
interface ButtonProps {
  variant?: 'primary' | 'secondary' | 'ghost' | 'danger'; // default 'primary'
  size?: 'sm' | 'md' | 'lg';                               // default 'md'
  isLoading?: boolean;
  disabled?: boolean;
  leftIcon?: ReactNode;
  rightIcon?: ReactNode;
  type?: 'button' | 'submit' | 'reset';                    // default 'button'
  onClick?: (e: React.MouseEvent<HTMLButtonElement>) => void;
  children: ReactNode;
}

// MoneyInput — value/onChange are decimal strings, e.g. "342000.00"; '' when empty
interface MoneyInputProps {
  value: string;
  onChange: (value: string) => void; // raw decimal string, unformatted
  currency?: 'USD';                  // default 'USD'; display prefix only
  disabled?: boolean;
  invalid?: boolean;
  sourceBadge?: SourceBadgeProps;    // shown when the value is auto-filled
  'aria-label': string;
}

// PercentInput — value/onChange are decimal strings in percent units, e.g. "7.500" = 7.5%
interface PercentInputProps {
  value: string;
  onChange: (value: string) => void;
  precision?: number;                // display decimals, default 3
  disabled?: boolean;
  invalid?: boolean;
  sourceBadge?: SourceBadgeProps;
  'aria-label': string;
}

// Table
interface TableColumn<T> {
  key: string;
  header: ReactNode;
  align?: 'left' | 'right' | 'center'; // default 'left'; 'right' applies tabular-nums
  render?: (row: T) => ReactNode;
}
interface TableProps<T> {
  columns: TableColumn<T>[];
  rows: T[];
  rowKey: (row: T) => string;
  onRowClick?: (row: T) => void;
  emptyState?: ReactNode;
  density?: 'compact' | 'comfortable'; // default 'comfortable'
}

// Tabs — the "check or flag-count" tab headers from the workspace shell (CQ-016)
interface TabItem {
  id: string;
  label: string;
  status?: 'complete' | 'flagged' | 'pending';
  flagCount?: number;
  disabled?: boolean;
}
interface TabsProps {
  items: TabItem[];
  activeId: string;
  onChange: (id: string) => void;
}

// StatusPill — the application status enum from system-design.md
type ApplicationStatus =
  | 'intake' | 'verifying' | 'needs_attention' | 'ready_to_price' | 'priced'
  | 'sent' | 'viewed' | 'option_selected' | 'inquiry' | 'stale' | 'withdrawn' | 'closed';
interface StatusPillProps {
  status: ApplicationStatus;
  size?: 'sm' | 'md'; // default 'md'
}
// tone map (fixed): intake=neutral, verifying=info, needs_attention=danger,
// ready_to_price=info, priced=success, sent=info, viewed=info,
// option_selected=success, inquiry=warning, stale=warning, withdrawn=neutral, closed=success

// SourceBadge — "every number shows its source" (system-design principle 2)
// mirrors CQ-007's FieldSource enum exactly (12 values, owner: CQ-007)
type SourceBadgeSource =
  | 'encompass' | 'rentcast' | 'airdna' | 'smartasset' | 'steadily' | 'optimal_blue'
  | 'credit_bureau' | 'property_search' | 'lo_entry' | 'formula' | 'default' | 'lo_override';
interface SourceBadgeProps {
  source: SourceBadgeSource;
  onRevert?: () => void; // rendered only when source === 'lo_override'
}

// Card
interface CardProps {
  title?: ReactNode;
  actions?: ReactNode;                 // top-right slot
  padding?: 'sm' | 'md' | 'lg';        // default 'md'
  children: ReactNode;
}

// Overlay — the primitive behind the tab-6 Add/Edit quote overlay (CQ-018)
interface OverlayProps {
  isOpen: boolean;
  onClose: () => void;
  title: ReactNode;
  size?: 'sm' | 'md' | 'lg' | 'full';   // default 'md'
  footer?: ReactNode;
  children: ReactNode;
}
```

## api-client generation

- Generator: `openapi-typescript` (schema → types) + `openapi-fetch` (typed fetch wrapper), both in `packages/api-client`.
- `make api-client` flow: (1) `uv run python backend/scripts/export_openapi.py` — CQ-004's script, imports the FastAPI `app` and dumps `app.openapi()` straight to `packages/api-client/openapi.json` (no server needed, no CLI flags); (2) `pnpm --filter @cq/api-client generate` runs `openapi-typescript openapi.json -o src/schema.d.ts` (relative to `packages/api-client`, since the JSON now lands inside that same package); (3) `packages/api-client/src/client.ts` exports `createApiClient(baseUrl: string)` wrapping `openapi-fetch` with that schema.
- Each app has a thin `src/lib/api-client.ts`: `export const api = createApiClient(process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000');`, reading `NEXT_PUBLIC_API_URL` from that app's own `.env.local`/`.env.example` (not CQ-002's root backend `.env.example`). Port `8000` is CQ-004's pinned backend dev-server port (`make api`), not just uvicorn's default.
- Nothing under `packages/api-client/src/schema.d.ts` is hand-edited (per `AGENTS.md` project map); it carries a `// GENERATED FILE — run \`make api-client\`` banner.

## Notes for the agent

- Frontend item: run `react-doctor` (`npx react-doctor -y`) in stages 4 and 5, scoped to `apps/lo-console`, `apps/borrower-portal`, `packages/ui`. `npx react-doctor --help` confirms flags used above (`-y`/`--yes` scans all workspace projects non-interactively; `--blocking <level>` sets the CI-failing severity, default `error`; `--json`/`--score` for machine-readable output in `post-dev.md`).
- Decision: styling is Tailwind v4 with CSS-variable tokens (not CSS modules) — v4's `@theme` directive maps 1:1 onto "tokens as CSS variables" and avoids a parallel JS config file.
- Decision: workspace package names are `@cq/ui` and `@cq/api-client` (private, unpublished); reconcile with CQ-002's spec if it names them differently.
- Decision: dev ports `3010`/`3020` picked from a one-time `lsof -iTCP -sTCP:LISTEN -P` scan on 2026-09-24; re-check if the local stack has changed before relying on them.
- Decision: `SourceBadgeSource` and `ApplicationStatus` string literals above are pinned to match CQ-007's `FieldSource`/`ApplicationStatus` Postgres enum values exactly (lower_snake_case, e.g. `'needs_attention'`, `'option_selected'`) — CQ-007 owns these names; this file was updated to match rather than the other way around, so the generated api-client types need no translation layer.
- Follow the agent loop in `AGENTS.md`. Log small decisions in `plan.md`; raise big gaps in Kaneo.
