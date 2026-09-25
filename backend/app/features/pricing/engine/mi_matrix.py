"""Conventional mortgage insurance (MI) rate table and lookup.

Annual MI rate applied to `loan_amount`, financed monthly as
`loan_amount * factor / 12`. Only meaningful when `strategy == PRIMARY` and
`ltv_pct > 0.80` — see `ScenarioInputs`/`compute_quote` for how strategy gates
this; `mi_factor` itself is a pure LTV x FICO lookup with no strategy
parameter (spec.md's binding public API).

`ltv_pct` is a 0-1 fraction (e.g. `0.95` for 95% LTV), matching every other
`*_pct` field on `ScenarioInputs`/`ConfigSnapshot`. `DEFAULT_MI_MATRIX`'s own
band bounds stay on a 0-100 percentage scale for readability (matching the
table in spec.md, "80.01-85.00%"); `mi_factor` converts its `ltv_pct`
argument to that scale internally before the band lookup.

Values are invented for realism — no MGIC/Radian rate card was supplied (see
spec.md's own "Decision" note). Swap `DEFAULT_MI_MATRIX` for a real rate card
without changing `mi_factor`'s signature if one becomes available.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Protocol

# (fico_upper_inclusive, annual_mi_rate); ordered lowest FICO band to highest.
# `None` marks the catch-all top band ("FICO >= previous band's upper + 1").
MiFicoBand = tuple[int | None, Decimal]

# (ltv_lower_exclusive, ltv_upper_inclusive, fico_bands), both LTV bounds on
# a 0-100 percentage scale, matching the table in spec.md ("80.01-85.00%").
# Bands are inclusive of their upper bound.
MiLtvRow = tuple[Decimal, Decimal, tuple[MiFicoBand, ...]]

MiMatrix = tuple[MiLtvRow, ...]


DEFAULT_MI_MATRIX: MiMatrix = (
    (
        Decimal("80.00"),
        Decimal("85.00"),
        (
            (679, Decimal("0.0058")),
            (719, Decimal("0.0042")),
            (759, Decimal("0.0031")),
            (None, Decimal("0.0019")),
        ),
    ),
    (
        Decimal("85.00"),
        Decimal("90.00"),
        (
            (679, Decimal("0.0086")),
            (719, Decimal("0.0062")),
            (759, Decimal("0.0044")),
            (None, Decimal("0.0030")),
        ),
    ),
    (
        Decimal("90.00"),
        Decimal("95.00"),
        (
            (679, Decimal("0.0113")),
            (719, Decimal("0.0083")),
            (759, Decimal("0.0059")),
            (None, Decimal("0.0039")),
        ),
    ),
    (
        Decimal("95.00"),
        Decimal("97.00"),
        (
            (679, Decimal("0.0186")),
            (719, Decimal("0.0135")),
            (759, Decimal("0.0096")),
            (None, Decimal("0.0063")),
        ),
    ),
)


class _HasMiMatrix(Protocol):
    """Structural type for the `config` parameter, to avoid importing
    `ConfigSnapshot` from `types.py` (which imports `DEFAULT_MI_MATRIX` from
    this module — importing back would be circular). A `@property` (rather
    than a plain attribute) matches `ConfigSnapshot`'s frozen, read-only
    field."""

    @property
    def mi_matrix(self) -> MiMatrix: ...


def mi_factor(ltv_pct: Decimal, fico: int, config: _HasMiMatrix) -> Decimal | None:
    """Look up the annual MI rate for `ltv_pct` (0-1 fraction, e.g. `0.95`) x `fico`.

    Returns `None` when `ltv_pct <= 0.80` (no MI required) or when `ltv_pct`
    is above the top tabulated band (out of range for the matrix supplied —
    `compute_quote` guards the >97% case itself with `LtvOutOfRangeError`
    rather than relying on this silent `None`). Does not know about
    `strategy`: callers (`compute_quote`) only invoke this when
    `strategy == PRIMARY`.
    """
    if ltv_pct <= Decimal("0.80"):
        return None
    ltv_percentage = ltv_pct * Decimal("100")
    for lower, upper, fico_bands in config.mi_matrix:
        if lower < ltv_percentage <= upper:
            for fico_upper, rate in fico_bands:
                if fico_upper is None or fico <= fico_upper:
                    return rate
    return None
