"""FastAPI app factory.

`create_app()` wires the pieces every feature relies on: exception
handling, the `/api/v1` feature-router registry, and the unprefixed
`/health` endpoint infra/monitoring hits directly. The module-level `app`
is what `uvicorn app.main:app` and `export_openapi.py` import.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.core.errors import register_exception_handlers
from app.core.registry import register_routers
from app.features.system.router import router as system_router


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(title="Clear Quote API")

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
