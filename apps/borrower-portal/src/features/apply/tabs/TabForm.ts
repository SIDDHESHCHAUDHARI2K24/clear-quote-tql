import type { JsonRecord } from "../paths";

/** What every tab component receives from `ApplyWizard`: the tab's raw
 * data record, a setter for one dotted path (which also (re)starts the 1 s
 * autosave timer), and a getter for that path's current, displayable
 * error (empty until the field is touched or "Next"/"Submit" is
 * pressed). */
export interface TabFormProps {
  data: JsonRecord;
  set: (path: string, value: unknown, touchedPath?: string) => void;
  errorFor: (path: string) => string | undefined;
  disabled: boolean;
}
