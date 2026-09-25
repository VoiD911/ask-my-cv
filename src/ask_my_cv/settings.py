from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, model_validator


class ModelConfig(BaseModel):
    id: str
    provider: Literal["fake", "ollama"]
    model: str = ""
    public: bool = True
    input_per_mtok: float = 0.0
    output_per_mtok: float = 0.0


class Settings(BaseModel):
    cv_path: Path = Path("data/cv.md")
    index_path: Path = Path("data/index.json")
    prompt_path: Path = Path("prompts/answer@v1.md")
    embed_dim: int = 256
    models: list[ModelConfig]
    default_model: str
    fallback_chain: list[str]
    ollama_url: str = "http://localhost:11434"
    top_k: int = 5
    injection_threshold: float = 0.5
    detector: Literal["heuristic", "onnx"] = "heuristic"
    model_manifest: Path = Path("models/prod.json")
    daily_cap_usd: float = 0.5
    per_visitor_limit: int = 10
    visitor_window_s: float = 3600.0
    stage_timeout_s: float = 20.0
    first_token_timeout_s: float = 8.0
    llm_deadline_s: float = 30.0
    allowed_contacts: list[str] = []
    visitor_salt: str = "change-me"

    @model_validator(mode="after")
    def _known_models(self) -> Settings:
        known = {m.id for m in self.models}
        unknown = ({self.default_model} | set(self.fallback_chain)) - known
        if unknown:
            raise ValueError(f"modèles inconnus dans la config : {sorted(unknown)}")
        return self

    def public_model_ids(self) -> set[str]:
        return {m.id for m in self.models if m.public}


_ENV_OVERRIDES = {"OLLAMA_URL": "ollama_url", "VISITOR_SALT": "visitor_salt"}


def load_settings(path: Path | None = None) -> Settings:
    path = path or Path(os.environ.get("ASK_SETTINGS", "settings.yaml"))
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    for env_name, field in _ENV_OVERRIDES.items():
        if value := os.environ.get(env_name):
            data[field] = value
    return Settings.model_validate(data)
