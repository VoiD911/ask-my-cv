from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from ask_my_cv.settings import ModelConfig, Settings, load_settings

YAML = """
default_model: ollama:gemma3
fallback_chain: [ollama:gemma3, fake:echo]
models:
  - {id: ollama:gemma3, provider: ollama, model: "gemma3:1b"}
  - {id: fake:echo, provider: fake}
  - {id: fake:hidden, provider: fake, public: false}
"""


def test_load_settings_from_yaml(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "settings.yaml"
    path.write_text(YAML, encoding="utf-8")
    monkeypatch.delenv("OLLAMA_URL", raising=False)
    settings = load_settings(path)
    assert settings.default_model == "ollama:gemma3"
    assert settings.public_model_ids() == {"ollama:gemma3", "fake:echo"}
    assert settings.ollama_url == "http://localhost:11434"


def test_env_overrides(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "settings.yaml"
    path.write_text(YAML, encoding="utf-8")
    monkeypatch.setenv("OLLAMA_URL", "http://ollama:11434")
    monkeypatch.setenv("VISITOR_SALT", "s3l")
    settings = load_settings(path)
    assert settings.ollama_url == "http://ollama:11434"
    assert settings.visitor_salt == "s3l"


def test_unknown_default_model_rejected() -> None:
    with pytest.raises(ValidationError):
        Settings(
            models=[ModelConfig(id="fake:echo", provider="fake")],
            default_model="nope",
            fallback_chain=["fake:echo"],
        )


def test_unknown_fallback_model_rejected() -> None:
    with pytest.raises(ValidationError):
        Settings(
            models=[ModelConfig(id="fake:echo", provider="fake")],
            default_model="fake:echo",
            fallback_chain=["fake:echo", "ghost"],
        )


def test_production_refuses_default_or_short_salt() -> None:
    base: dict[str, Any] = dict(
        models=[ModelConfig(id="fake:echo", provider="fake")],
        default_model="fake:echo",
        fallback_chain=["fake:echo"],
        environment="prod",
    )
    with pytest.raises(ValidationError):
        Settings(**base)
    with pytest.raises(ValidationError):
        Settings(**base, visitor_salt="court")
    assert Settings(**base, visitor_salt="s" * 32).environment == "prod"


def test_environment_override(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "settings.yaml"
    path.write_text(YAML, encoding="utf-8")
    monkeypatch.setenv("ASK_ENVIRONMENT", "prod")
    monkeypatch.setenv("VISITOR_SALT", "s" * 32)
    assert load_settings(path).environment == "prod"


def minimal(**extra: object) -> dict:
    return {
        "models": [{"id": "fake:echo", "provider": "fake"}],
        "default_model": "fake:echo",
        "fallback_chain": ["fake:echo"],
        **extra,
    }


@pytest.mark.parametrize(
    "extra",
    [
        {"top_k": 0},
        {"top_k": 21},
        {"injection_threshold": 0.0},
        {"injection_threshold": 1.0},
        {"per_visitor_limit": 0},
        {"daily_cap_usd": -1},
        {"stage_timeout_s": 0},
        {"first_token_timeout_s": 0},
    ],
)
def test_out_of_range_settings_are_rejected(extra: dict) -> None:
    with pytest.raises(ValidationError):
        Settings.model_validate(minimal(**extra))


def test_ollama_model_requires_a_model_name() -> None:
    data = minimal()
    data["models"].append({"id": "ollama:x", "provider": "ollama"})
    with pytest.raises(ValidationError):
        Settings.model_validate(data)


def test_ledger_protocol_exposes_spend_by_provider() -> None:
    from ask_my_cv.budget import BudgetLedger

    assert "spent_by_provider" in dir(BudgetLedger)


@pytest.mark.parametrize(
    "origins",
    [
        ["*"],
        ["http://portfolio.example"],
        ["https://ok.example", "*"],
        ["http://localhost.evil.com"],
        ["https://ok.example/path"],
        ["https://"],
    ],
)
def test_cors_origins_are_restricted(origins: list[str]) -> None:
    with pytest.raises(ValidationError):
        Settings.model_validate(minimal(cors_origins=origins))


def test_cors_allows_https_and_localhost() -> None:
    s = Settings.model_validate(
        minimal(
            cors_origins=[
                "https://portfolio.example",
                "http://localhost:3000",
                "http://127.0.0.1:8080",
            ]
        )
    )
    assert len(s.cors_origins) == 3
