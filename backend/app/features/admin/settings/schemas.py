"""`GET /admin/settings` shapes (spec.md "Settings", Admin, read-only)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel


class SettingValue(BaseModel):
    key: str
    value: Any
    description: str | None
    source: Literal["settings_table", "code_default"]


class SettingsResponse(BaseModel):
    settings: list[SettingValue]
