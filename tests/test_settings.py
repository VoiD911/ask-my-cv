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
