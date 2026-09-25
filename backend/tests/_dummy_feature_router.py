"""A throwaway feature router used only by test_registry.py::test_dummy_router_registers.

Not collected by pytest (filename doesn't match `test_*.py`); demonstrates
that adding a dotted path to `FEATURE_ROUTERS` is enough to register a new
feature's routes without touching `main.py`.
"""

from fastapi import APIRouter

router = APIRouter()


@router.get("/dummy")
def get_dummy() -> dict[str, str]:
    return {"dummy": "ok"}
