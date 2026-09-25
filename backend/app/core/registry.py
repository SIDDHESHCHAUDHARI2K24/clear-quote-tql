"""Feature-router registration.

To add a feature (CQ-007 onward): create the sub-feature package with its
own `router.py` exposing a module-level `router = APIRouter()`, then append
its dotted module path here. `register_routers` mounts every listed
router under `/api/v1` without anyone touching `main.py`.
"""

from importlib import import_module

from fastapi import FastAPI

FEATURE_ROUTERS: list[str] = [
    "app.features.system.router",
]


def register_routers(app: FastAPI) -> None:
    for module_path in FEATURE_ROUTERS:
        module = import_module(module_path)
        app.include_router(module.router, prefix="/api/v1")
