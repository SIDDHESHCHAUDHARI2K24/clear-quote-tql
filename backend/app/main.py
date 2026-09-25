"""FastAPI app factory.

`create_app()` wires the pieces every feature relies on: exception
handling, the `/api/v1` feature-router registry, and the unprefixed
`/health` endpoint infra/monitoring hits directly. The module-level `app`
is what `uvicorn app.main:app` and `export_openapi.py` import.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.core.errors import register_exception_handlers
from app.core.registry import register_routers
from app.core.valkey import close_valkey
from app.features.quotes.report.schemas import report_view_model_openapi_components
from app.features.system.router import router as system_router


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    yield
    # CQ-014: releases the shared Valkey connection (OTP/session store) on
    # shutdown instead of leaking it across process restarts/reloads.
    await close_valkey()


def _register_report_view_model_schema(app: FastAPI) -> None:
    """CQ-021: `ReportViewModel` (backend/app/features/quotes/report/schemas.py)
    has no endpoint of its own yet -- its builder is pure and reads no DB;
    CQ-019/CQ-022 will expose it through real endpoints later. Rather than
    add a throwaway endpoint just to get the type into the OpenAPI schema
    (spec.md calls that "not ideal"), merge its `components/schemas` entries
    into `app.openapi()`'s output directly, so `make api-client` generates
    the TypeScript type today. See CQ-021 plan.md Decision 1."""
    original_openapi = app.openapi

    def custom_openapi() -> dict[str, object]:
        schema = original_openapi()
        schema.setdefault("components", {}).setdefault("schemas", {}).update(
            report_view_model_openapi_components()
        )
        return schema

    app.openapi = custom_openapi  # type: ignore[method-assign]


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(title="Clear Quote API", lifespan=_lifespan)

    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    register_routers(app)
    register_exception_handlers(app)
    _register_report_view_model_schema(app)

    # Mounted directly (not through the registry) so `/health` stays
    # unprefixed regardless of what `FEATURE_ROUTERS` contains.
    app.include_router(system_router, tags=["system"])

    return app


app = create_app()
