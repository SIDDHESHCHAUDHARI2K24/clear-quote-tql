"""Small SQL helpers shared across features.

`escape_like` was originally `notifications/outbox/service.py::_escape_like`
(a code-review finding there: an unescaped free-text `q` let `%`/`_` act as
SQL LIKE wildcards, e.g. `100%` matching any subject starting with `100`).
Moved here (review round 1, CQ-026) so every `ilike(...)` free-text search
in the codebase -- outbox, clients, and `applications/listing`'s `q` --
shares one implementation instead of three copies drifting apart.
"""

from __future__ import annotations

LIKE_ESCAPE_CHAR = "\\"
"""Pass as `ilike(pattern, escape=LIKE_ESCAPE_CHAR)` alongside `escape_like`."""


def escape_like(value: str) -> str:
    """Escapes `%`, `_` and the escape character itself so a free-text
    search term matches literally when interpolated into a `LIKE`/`ILIKE`
    pattern (e.g. wrapped as `f"%{escape_like(value)}%"`)."""
    return (
        value.replace(LIKE_ESCAPE_CHAR, LIKE_ESCAPE_CHAR * 2)
        .replace("%", r"\%")
        .replace("_", r"\_")
    )
