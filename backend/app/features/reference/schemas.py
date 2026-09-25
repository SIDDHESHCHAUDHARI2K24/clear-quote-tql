from __future__ import annotations

from pydantic import BaseModel


class StateMetros(BaseModel):
    state: str
    metros: list[str]


class MetrosResponse(BaseModel):
    states: list[StateMetros]
