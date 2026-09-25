from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

StageStatus = Literal["ok", "blocked", "error", "fallback"]


class StageStart(BaseModel):
    type: Literal["stage.start"] = "stage.start"
    name: str
    ts: float


class StageEnd(BaseModel):
    type: Literal["stage.end"] = "stage.end"
    name: str
    status: StageStatus
    duration_ms: float
    attrs: dict[str, Any] = Field(default_factory=dict)


class Token(BaseModel):
    type: Literal["token"] = "token"
    text: str


class Done(BaseModel):
    type: Literal["done"] = "done"
    tokens_in: int
    tokens_out: int
    cost_usd: float
    latency_ms: float
    sources: list[str]
    answer_override: str | None = None


Event = StageStart | StageEnd | Token | Done
