from __future__ import annotations

import os
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from ask_my_cv.visitor import TrustedProxy


class ConfigError(ValueError):
    """Configuration invalide (message sans les valeurs saisies)."""


class ModelConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    provider: Literal["fake", "ollama", "bedrock"]
    model: str = ""
    public: bool = True
    input_per_mtok: float = Field(default=0.0, ge=0, allow_inf_nan=False)
    output_per_mtok: float = Field(default=0.0, ge=0, allow_inf_nan=False)

    @model_validator(mode="after")
    def _ollama_needs_model(self) -> ModelConfig:
        if self.provider in ("ollama", "bedrock") and not self.model:
            raise ValueError(f"{self.id} : 'model' est obligatoire pour {self.provider}")
        return self


class Settings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cv_path: Path = Path("data/cv.md")
    index_path: Path = Path("data/index.json")
    prompt_path: Path = Path("prompts/answer@v2.md")
    embed_dim: int = Field(default=256, ge=1, le=4096)
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
    aws_region: str = "ca-central-1"
    embedder: Literal["hash", "bedrock"] = "hash"
    embed_model: str = "amazon.titan-embed-text-v2:0"
    vector_store: Literal["file", "dynamodb"] = "file"
    chunks_table: str = "ask-my-cv-chunks"
    ledger: Literal["memory", "dynamodb"] = "memory"
    ledger_table: str = "ask-my-cv-ledger"
    tracing: list[Literal["console", "cloudwatch", "langfuse"]] = []
    langfuse_endpoint: str = "https://us.cloud.langfuse.com/api/public/otel/v1/traces"

    @field_validator("ollama_url")
    @classmethod
    def _ollama_url_is_http(cls, value: str) -> str:
        parts = urlsplit(value)
        if parts.scheme not in ("http", "https") or not parts.hostname:
            raise ValueError("ollama_url doit être une URL http(s) avec un hôte")
        return value

    @model_validator(mode="after")
    def _bedrock_embedder_dimension(self) -> Settings:
        if self.embedder == "bedrock" and self.embed_dim not in (256, 512, 1024):
            raise ValueError(
                f"Titan V2 n'accepte que les dimensions 256, 512 ou 1024 (reçu {self.embed_dim})"
            )
        return self

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
            parts = urlsplit(origin)
            if parts.path or parts.query or parts.fragment:
                raise ValueError(
                    f"origine CORS invalide : {origin!r} ne doit contenir ni chemin ni requête"
                )
            is_https = parts.scheme == "https" and bool(parts.hostname)
            is_local_http = parts.scheme == "http" and parts.hostname in {
                "localhost",
                "127.0.0.1",
            }
            if not (is_https or is_local_http):
                raise ValueError(
                    f"origine CORS invalide : {origin!r} doit être en 'https://' "
                    "(sauf localhost/127.0.0.1 en développement)"
                )
            try:
                port = parts.port
            except ValueError as exc:
                raise ValueError(f"origine CORS invalide : {origin!r} : {exc}") from None
            canonical = f"{parts.scheme}://{parts.hostname}{f':{port}' if port else ''}"
            if canonical != origin:
                raise ValueError(
                    f"origine CORS invalide : {origin!r} n'est pas une origine canonique "
                    f"(attendu {canonical!r})"
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
    try:
        return Settings.model_validate(data)
    except ValidationError as exc:
        details = "; ".join(
            f"{'.'.join(str(p) for p in e['loc']) or 'settings'}: {e['msg']}"
            for e in exc.errors(include_input=False, include_url=False, include_context=False)
        )
        raise ConfigError(f"configuration invalide : {details}") from None
