import { cx } from "../utils/cx";
import type { ReportOptionData } from "./types";

export interface OptionSwitcherProps {
  options: ReportOptionData[];
  selectedId: string;
  onChange: (quoteId: string) => void;
}

export function OptionSwitcher({ options, selectedId, onChange }: OptionSwitcherProps) {
  return (
    <div role="radiogroup" aria-label="Priced options" className="flex flex-wrap gap-2">
      {options.map((option) => {
        const isSelected = option.quote_id === selectedId;
        return (
          <button
            key={option.quote_id}
            type="button"
            role="radio"
            aria-checked={isSelected}
            onClick={() => onChange(option.quote_id)}
            className={cx(
              "inline-flex items-center gap-1.5 rounded-full border px-4 py-2 text-sm font-medium transition-colors",
              isSelected
                ? "border-navy-500 bg-navy-500 text-neutral-0"
                : "border-neutral-200 bg-neutral-0 text-navy-900 hover:border-navy-300",
            )}
          >
            {option.recommended && (
              <span aria-hidden="true" className="text-sage-300">
                ★
              </span>
            )}
            {option.label}
            {option.recommended && <span className="sr-only">(recommended)</span>}
          </button>
        );
      })}
    </div>
  );
}
