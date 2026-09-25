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


class LLMProgress(BaseModel):
    """Progression de la génération : un compteur, jamais de texte."""

    type: Literal["llm.progress"] = "llm.progress"
    tokens: int


class Answer(BaseModel):
    """La réponse, émise uniquement après le garde-fou de sortie."""

    type: Literal["answer"] = "answer"
    text: str


class Done(BaseModel):
    type: Literal["done"] = "done"
    tokens_in: int
    tokens_out: int
    cost_usd: float
    latency_ms: float
    sources: list[str]
    answer_override: str | None = None
    trace_id: str | None = None


Event = StageStart | StageEnd | LLMProgress | Answer | Done
