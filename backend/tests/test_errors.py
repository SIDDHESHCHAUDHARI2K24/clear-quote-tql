"""AC4: raising each `AppError` subclass returns the pinned error JSON shape."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.errors import (
    AppError,
    AuthenticationError,
    ConflictError,
    IntegrationError,
    NotFoundError,
    ValidationAppError,
    register_exception_handlers,
)


def _build_test_app() -> FastAPI:
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/raise/not-found")
    def _raise_not_found() -> None:
        raise NotFoundError("Application 123 not found")

    @app.get("/raise/validation")
    def _raise_validation() -> None:
        raise ValidationAppError("Bad field", details={"field": "income"})

    @app.get("/raise/conflict")
    def _raise_conflict() -> None:
        raise ConflictError("Already exists")

    @app.get("/raise/authentication")
    def _raise_authentication() -> None:
        raise AuthenticationError("No credentials")

    @app.get("/raise/integration")
    def _raise_integration() -> None:
        raise IntegrationError("Upstream failed")

    @app.get("/raise/unhandled")
    def _raise_unhandled() -> None:
        raise RuntimeError("boom")

    return app


@pytest.mark.parametrize(
    ("path", "status_code", "code"),
    [
        ("/raise/not-found", 404, "NOT_FOUND"),
        ("/raise/validation", 422, "VALIDATION_ERROR"),
        ("/raise/conflict", 409, "CONFLICT"),
        ("/raise/authentication", 401, "AUTHENTICATION_ERROR"),
        ("/raise/integration", 502, "INTEGRATION_ERROR"),
    ],
)
def test_each_apperror_subclass(path: str, status_code: int, code: str) -> None:
    client = TestClient(_build_test_app(), raise_server_exceptions=False)

    response = client.get(path)

    assert response.status_code == status_code
    body = response.json()
    assert body["error"]["code"] == code
    assert isinstance(body["error"]["message"], str) and body["error"]["message"]
    assert isinstance(body["error"]["details"], dict)


def test_unhandled_exception_returns_internal_error() -> None:
    client = TestClient(_build_test_app(), raise_server_exceptions=False)

    response = client.get("/raise/unhandled")

    assert response.status_code == 500
    assert response.json() == {
        "error": {
            "code": "INTERNAL_ERROR",
            "message": "Internal server error",
            "details": {},
        }
    }


def test_apperror_status_and_code_can_be_overridden_per_instance() -> None:
    err = IntegrationError("Pricing rejected", status_code=422, code="PRICING_VALIDATION_ERROR")

    assert isinstance(err, AppError)
    assert err.status_code == 422
    assert err.code == "PRICING_VALIDATION_ERROR"
