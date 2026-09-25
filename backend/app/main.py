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
from app.features.system.router import router as system_router


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    yield
    # CQ-014: releases the shared Valkey connection (OTP/session store) on
    # shutdown instead of leaking it across process restarts/reloads.
    await close_valkey()


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

    # Mounted directly (not through the registry) so `/health` stays
    # unprefixed regardless of what `FEATURE_ROUTERS` contains.
    app.include_router(system_router, tags=["system"])

    return app


app = create_app()
