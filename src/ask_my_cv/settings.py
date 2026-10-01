from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from ask_my_cv.visitor import TrustedProxy

logger = logging.getLogger(__name__)


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
    prompt_path: Path = Path("prompts/answer@v7.md")
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
    # jeton des évaluations automatiques (en-tête X-Eval-Token) : jamais dans un repr ni un log
    eval_token: str | None = Field(default=None, repr=False)
    eval_limit_per_window: int = Field(default=300, ge=1)
    # jeton du trafic interne (en-tête X-Internal-Token : tests de fumée, propriétaire) : il ne
    # change que le classement analytique (`xops.traffic`), jamais le quota ni le plafond
    internal_token: str | None = Field(default=None, repr=False)
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
    # Garde-fou Bedrock « annonces » (#118) : second avis sur les annonces collées. Désactivé
    # tant que l'identifiant et la version publiée ne sont pas fournis (local, CI, ou code
    # déployé avant `terraform apply`) : le classifieur décide alors seul.
    guardrail_id: str | None = None
    guardrail_version: str | None = None
    guardrail_timeout_s: float = Field(default=2.0, gt=0.0, le=10.0)
    guardrail_min_chars: int = Field(default=400, ge=1)
    # disjoncteur (par processus) : échec fermé des annonces après ces échecs sur la fenêtre
    # glissante (tous visiteurs, dont au moins min_visitors distincts / un visiteur)
    guardrail_breaker_failures: int = Field(default=5, ge=1)
    guardrail_breaker_visitor_failures: int = Field(default=3, ge=1)
    guardrail_breaker_cooldown_s: float = Field(default=60.0, gt=0.0)
    guardrail_breaker_window_s: float = Field(default=60.0, gt=0.0)
    guardrail_breaker_min_visitors: int = Field(default=3, ge=1)

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
    def _guardrail_is_complete(self) -> Settings:
        if (self.guardrail_id is None) != (self.guardrail_version is None):
            raise ValueError("guardrail_id et guardrail_version vont ensemble")
        if self.guardrail_version is not None and not re.fullmatch(
            r"[0-9]+", self.guardrail_version
        ):
            raise ValueError("guardrail_version doit être une version publiée (nombre, pas DRAFT)")
        if self.guardrail_id is not None and not self.guardrail_id:
            raise ValueError("guardrail_id ne doit pas être vide")
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
    def _eval_token_is_strong(self) -> Settings:
        # message sans la valeur ; un jeton vide égalerait un en-tête absent
        if self.eval_token is not None and (
            not self.eval_token or (self.environment == "prod" and len(self.eval_token) < 32)
        ):
            raise ValueError("EVAL_TOKEN doit être non vide (au moins 32 caractères en production)")
        if self.internal_token is not None and (
            not self.internal_token
            or (self.environment == "prod" and len(self.internal_token) < 32)
        ):
            raise ValueError(
                "INTERNAL_TOKEN doit être non vide (au moins 32 caractères en production)"
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
    "EVAL_TOKEN": "eval_token",
    "INTERNAL_TOKEN": "internal_token",
    # sorties Terraform guardrail_annonces_id / _version (infra/prod/lambda.tf)
    "ASK_GUARDRAIL_ID": "guardrail_id",
    "ASK_GUARDRAIL_VERSION": "guardrail_version",
}


def load_settings(path: Path | None = None) -> Settings:
    path = path or Path(os.environ.get("ASK_SETTINGS", "settings.yaml"))
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    for env_name, field in _ENV_OVERRIDES.items():
        value = os.environ.get(env_name)
        if value is None:
            continue
        if not value.strip():
            # variable présente mais vide (ex. sortie Terraform vide) : traitée comme absente,
            # et signalée plutôt que d'effacer silencieusement la valeur du fichier
            logger.warning("variable %s vide : ignorée", env_name)
            continue
        data[field] = value
    try:
        return Settings.model_validate(data)
    except ValidationError as exc:
        details = "; ".join(
            f"{'.'.join(str(p) for p in e['loc']) or 'settings'}: {e['msg']}"
            for e in exc.errors(include_input=False, include_url=False, include_context=False)
        )
        raise ConfigError(f"configuration invalide : {details}") from None
