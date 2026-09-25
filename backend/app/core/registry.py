"""Feature-router registration.

To add a feature (CQ-007 onward): create the sub-feature package with its
own `router.py` exposing a module-level `router = APIRouter()`, then append
its dotted module path here. `register_routers` mounts every listed
router under `/api/v1` without anyone touching `main.py`.

`system` is not a `/api/v1` feature — `main.create_app()` mounts it
directly and unprefixed for the `/health` contract — so it never goes in
this list. `FEATURE_ROUTERS` starts empty; CQ-007 onward appends here.
"""

from importlib import import_module

from fastapi import FastAPI

FEATURE_ROUTERS: list[str] = [
    "app.features.pricing.enrichment.router",
    "app.features.pricing.scenarios.router",
]


def register_routers(app: FastAPI) -> None:
    for module_path in FEATURE_ROUTERS:
        module = import_module(module_path)
        app.include_router(module.router, prefix="/api/v1")
