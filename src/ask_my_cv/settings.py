from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, model_validator

from ask_my_cv.visitor import TrustedProxy


class ModelConfig(BaseModel):
    id: str
    provider: Literal["fake", "ollama"]
    model: str = ""
    public: bool = True
    input_per_mtok: float = 0.0
    output_per_mtok: float = 0.0

    @model_validator(mode="after")
    def _ollama_needs_model(self) -> ModelConfig:
        if self.provider == "ollama" and not self.model:
            raise ValueError(f"{self.id} : 'model' est obligatoire pour Ollama")
        return self


class Settings(BaseModel):
    cv_path: Path = Path("data/cv.md")
    index_path: Path = Path("data/index.json")
    prompt_path: Path = Path("prompts/answer@v2.md")
    embed_dim: int = 256
    models: list[ModelConfig]
    default_model: str
    fallback_chain: list[str]
    ollama_url: str = "http://localhost:11434"
    top_k: int = Field(default=5, ge=1, le=20)
    injection_threshold: float = Field(default=0.5, gt=0.0, lt=1.0)
    detector: Literal["heuristic", "onnx"] = "heuristic"
    model_manifest: Path = Path("models/prod.json")
    daily_cap_usd: float = Field(default=0.5, ge=0.0)
    per_visitor_limit: int = Field(default=10, ge=1)
    visitor_window_s: float = Field(default=3600.0, gt=0.0)
    stage_timeout_s: float = Field(default=20.0, gt=0.0)
    first_token_timeout_s: float = Field(default=8.0, gt=0.0)
    llm_deadline_s: float = Field(default=30.0, gt=0.0)
    allowed_contacts: list[str] = []
    visitor_salt: str = "change-me"
    environment: Literal["dev", "prod"] = "dev"
    trusted_proxy: TrustedProxy = "none"
    cors_origins: list[str] = []

    @model_validator(mode="after")
    def _known_models(self) -> Settings:
        known = {m.id for m in self.models}
        unknown = ({self.default_model} | set(self.fallback_chain)) - known
        if unknown:
            raise ValueError(f"modèles inconnus dans la config : {sorted(unknown)}")
        return self

    @model_validator(mode="after")
    def _production_secret(self) -> Settings:
        if self.environment == "prod" and (
            self.visitor_salt == "change-me" or len(self.visitor_salt) < 32
        ):
            raise ValueError(
                "en production, VISITOR_SALT doit être un secret d'au moins 32 caractères"
            )
        return self

    @model_validator(mode="after")
    def _cors_origins_are_restricted(self) -> Settings:
        for origin in self.cors_origins:
            if origin == "*":
                raise ValueError("cors_origins ne doit pas contenir '*'")
            if origin.startswith(("http://localhost", "http://127.0.0.1")):
                continue
            if not origin.startswith("https://"):
                raise ValueError(
                    f"origine CORS invalide : {origin!r} doit commencer par 'https://' "
                    "(sauf localhost/127.0.0.1 en développement)"
                )
        return self

    def public_model_ids(self) -> set[str]:
        return {m.id for m in self.models if m.public}


_ENV_OVERRIDES = {
    "OLLAMA_URL": "ollama_url",
    "VISITOR_SALT": "visitor_salt",
    "ASK_ENVIRONMENT": "environment",
}


def load_settings(path: Path | None = None) -> Settings:
    path = path or Path(os.environ.get("ASK_SETTINGS", "settings.yaml"))
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    for env_name, field in _ENV_OVERRIDES.items():
        if value := os.environ.get(env_name):
            data[field] = value
    return Settings.model_validate(data)
