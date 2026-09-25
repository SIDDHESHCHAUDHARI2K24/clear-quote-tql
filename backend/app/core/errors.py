"""Pinned application error shape.

Every `AppError` (and subclass) raised anywhere in the backend is turned by
`register_exception_handlers` into the JSON body:

    {"error": {"code": "...", "message": "...", "details": {}}}

Subclasses fix a default `code`/`status_code`, but any instance may override
either (see CQ-009's `PricingValidationError`, which subclasses
`IntegrationError` but reports 422 instead of 502).
"""

from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


class AppError(Exception):
    """Base class for all application errors with a stable HTTP+JSON shape."""

    code: str = "APP_ERROR"
    status_code: int = 400

    def __init__(
        self,
        message: str,
        *,
        code: str | None = None,
        status_code: int | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.code = code if code is not None else self.code
        self.status_code = status_code if status_code is not None else self.status_code
        self.details = details if details is not None else {}


class NotFoundError(AppError):
    code = "NOT_FOUND"
    status_code = 404


class ValidationAppError(AppError):
    code = "VALIDATION_ERROR"
    status_code = 422


class ConflictError(AppError):
    code = "CONFLICT"
    status_code = 409


class AuthenticationError(AppError):
    code = "AUTHENTICATION_ERROR"
    status_code = 401


class IntegrationError(AppError):
    code = "INTEGRATION_ERROR"
    status_code = 502


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _handle_app_error(request: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": {
                    "code": exc.code,
                    "message": exc.message,
                    "details": exc.details,
                }
            },
        )

    @app.exception_handler(Exception)
    async def _handle_unhandled_error(request: Request, exc: Exception) -> JSONResponse:
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "code": "INTERNAL_ERROR",
                    "message": "Internal server error",
                    "details": {},
                }
            },
        )
