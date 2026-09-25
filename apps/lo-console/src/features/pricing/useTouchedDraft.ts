"use client";

import { useEffect, useRef, useState } from "react";

// PR review round (fresh stage-6, PR #9, MINOR): the touched-ref +
// reset-on-prop-change state machine behind an enriched field's inline
// edit was duplicated verbatim between `EnrichedPercentField` and
// `EnrichedMoneyField` -- this hook is the one copy.
//
// `toDisplay` must be a stable function reference (a module-level
// function, not an inline arrow) -- it's an effect dependency, and a new
// identity every render would re-run the reset effect every render.
export function useTouchedDraft(
  wireValue: string | null | undefined,
  toDisplay: (value: string | null) => string,
) {
  const [draft, setDraft] = useState(() => toDisplay(wireValue ?? null));
  // A `ref`, not `useState`: it's read only inside `commit` (itself only
  // called from an `onBlur` handler), so it never needs to trigger a
  // render -- and `useState` here trips two `react-doctor` findings
  // ("state only used in handlers" / "state adjusted after a prop
  // change"), verified while building this fix (score 74 -> 71 -> 74).
  const touched = useRef(false);

  useEffect(() => {
    setDraft(toDisplay(wireValue ?? null));
    touched.current = false;
  }, [wireValue, toDisplay]);

  const handleChange = (value: string) => {
    setDraft(value);
    touched.current = true;
  };

  /**
   * Call from the input's `onBlur`. `toWire` converts the typed display
   * text to the wire value to send (or `null` if the draft doesn't
   * resolve to a committable value, e.g. an unparseable percent string).
   *
   * Returns the wire value to send to `onOverride`, or `null` when
   * nothing should be sent -- either because the field was never
   * actually edited (`touched` is only set by `handleChange`, so a plain
   * focus+blur is always a no-op regardless of any display-rounding
   * artifact in `toDisplay`/`toWire`), or because the edited value is
   * numerically the same as `wireValue` just spelled differently (e.g.
   * retyping "0.64" over a field whose "0.0064" fraction displays as
   * "0.640" -- PR #9's second review pass). `wireValue` can be `null` (a
   * `field_values` row with no value yet); `Number(null)` is `0`, not
   * `NaN`, so the numeric-equality check is skipped in that case and any
   * edit always commits.
   */
  function commit(toWire: (draftValue: string) => string | null): string | null {
    if (!touched.current || draft === "") return null;
    touched.current = false;
    const wire = toWire(draft);
    if (wire === null) return null;
    if (wireValue != null && Number(wire) === Number(wireValue)) return null;
    return wire;
  }

  return { draft, handleChange, commit };
}
