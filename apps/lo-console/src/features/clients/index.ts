export { ClientsTable } from "./components/ClientsTable";
export type { ClientsTableProps } from "./components/ClientsTable";

export { ClientsFilterBar } from "./components/ClientsFilterBar";
export type { ClientsFilterBarProps } from "./components/ClientsFilterBar";

export { ClientDetailHeader } from "./components/ClientDetailHeader";
export type { ClientDetailHeaderProps } from "./components/ClientDetailHeader";

export { ClientDetailView } from "./components/ClientDetailView";
export type { ClientDetailViewProps } from "./components/ClientDetailView";

export { SentVersionsTable } from "./components/SentVersionsTable";
export type { SentVersionsTableProps } from "./components/SentVersionsTable";

export { fetchClient, fetchClients } from "./api";
export type { ClientListQuery } from "./api";

export {
  DEFAULT_FILTERS,
  DEFAULT_PAGE_SIZE,
  DEFAULT_SORT,
  HAS_ACTIVE_OPTIONS,
  SORT_OPTIONS,
  filtersToApiQuery,
  filtersToSearchParams,
  hasActiveFilters,
  parseFiltersFromSearchParams,
} from "./filters";
export type { ClientFilters } from "./filters";

export { useClientFilters } from "./useClientFilters";
export type { UseClientFiltersResult } from "./useClientFilters";

export type { ClientDetail, ClientListResponse, ClientRow, ClientSentVersion } from "./types";
