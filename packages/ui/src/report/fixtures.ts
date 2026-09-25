// Both apps' `/gallery/report` pages need these fixtures, but `@cq/ui`'s
// `package.json` "exports" only opens up "." and "./styles/tokens.css" --
// a deep import of a JSON file under `report/__fixtures__/` from an app
// wouldn't resolve. Re-exporting them here (keyed, typed) through the
// normal package entrypoint is the fix; `build_report_fixtures.py` is the
// only place that writes the underlying JSON files, this module never
// edits them.
import danielOrtiz from "./__fixtures__/daniel_ortiz.json";
import kathleenMcreynolds from "./__fixtures__/kathleen_mcreynolds.json";
import marcusHale from "./__fixtures__/marcus_hale.json";
import marcusHaleExpired from "./__fixtures__/marcus_hale_expired.json";
import priyaNair from "./__fixtures__/priya_nair.json";
import priyaNairSuperseded from "./__fixtures__/priya_nair_superseded.json";
import type { ReportViewModelData } from "./types";

export interface ReportFixture {
  key: string;
  title: string;
  viewModel: ReportViewModelData;
}

export const REPORT_FIXTURES: ReportFixture[] = [
  {
    key: "marcus_hale",
    title: "Marcus Hale — STR, Tampa FL",
    viewModel: marcusHale as ReportViewModelData,
  },
  {
    key: "marcus_hale_expired",
    title: "Marcus Hale — expired (21+ days)",
    viewModel: marcusHaleExpired as ReportViewModelData,
  },
  {
    key: "kathleen_mcreynolds",
    title: "Kathleen McReynolds — LTR, property TBD",
    viewModel: kathleenMcreynolds as ReportViewModelData,
  },
  {
    key: "priya_nair",
    title: "Priya Nair — primary, 20% down",
    viewModel: priyaNair as ReportViewModelData,
  },
  {
    key: "priya_nair_superseded",
    title: "Priya Nair — superseded by a newer sent version",
    viewModel: priyaNairSuperseded as ReportViewModelData,
  },
  {
    key: "daniel_ortiz",
    title: "Daniel Ortiz — primary with MI, 5% down",
    viewModel: danielOrtiz as ReportViewModelData,
  },
];
