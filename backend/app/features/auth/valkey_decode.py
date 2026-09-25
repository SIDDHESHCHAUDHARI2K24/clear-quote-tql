"""Shared bytes/str decode-response workaround for Valkey reads.

The Valkey client is always constructed with `decode_responses=True` (see
`core/valkey.py`), so every value it returns is `str` at runtime — but
redis-py's type stubs still type most read commands as `bytes | str` (or
`dict[bytes | str, bytes | str]`), since the library can't see that flag
statically. `decode_value` centralizes the therefore-safe narrowing so
`otp/service.py` and `sessions/service.py` don't each carry their own copy.
"""


def decode_value(value: bytes | str) -> str:
    return value.decode("utf-8") if isinstance(value, bytes) else value
