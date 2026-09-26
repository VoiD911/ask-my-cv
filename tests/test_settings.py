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


def test_bedrock_model_requires_a_model_id() -> None:
    data = minimal()
    data["models"].append({"id": "bedrock:x", "provider": "bedrock"})
    with pytest.raises(ValidationError):
        Settings.model_validate(data)


@pytest.mark.parametrize("field", ["input_per_mtok", "output_per_mtok"])
def test_model_price_rejects_negative_values(field: str) -> None:
    with pytest.raises(ValidationError):
        ModelConfig.model_validate({"id": "fake:echo", "provider": "fake", field: -0.01})


@pytest.mark.parametrize("field", ["input_per_mtok", "output_per_mtok"])
def test_model_price_rejects_nan(field: str) -> None:
    with pytest.raises(ValidationError):
        ModelConfig.model_validate({"id": "fake:echo", "provider": "fake", field: float("nan")})


@pytest.mark.parametrize("dim", [0, 300, 2048])
def test_bedrock_embedder_needs_a_titan_dimension(dim: int) -> None:
    with pytest.raises(ValidationError):
        Settings.model_validate(minimal(embedder="bedrock", embed_dim=dim))


def test_production_aws_settings_load(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VISITOR_SALT", "s" * 48)
    settings = load_settings(Path("settings.aws.yaml"))
    assert (settings.environment, settings.aws_region) == ("prod", "ca-central-1")
    assert (settings.embedder, settings.vector_store, settings.ledger) == (
        "bedrock",
        "dynamodb",
        "dynamodb",
    )
    assert settings.trusted_proxy == "cloudfront" and settings.detector == "onnx"
    assert set(settings.tracing) == {"cloudwatch", "langfuse"}
    haiku = next(m for m in settings.models if m.provider == "bedrock")
    assert haiku.model.startswith("us.anthropic.claude-haiku-4-5")


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
        ["HTTPS://A.EXAMPLE"],
        ["https://A.example"],
        ["https://user:pw@a.example"],
        ["https://a.example:99999"],
        ["https://a.example:abc"],
        [" https://a.example"],
        ["https://a.example?"],
        ["https://a.example#"],
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
                "https://a.example:8443",
            ]
        )
    )
    assert len(s.cors_origins) == 4


def test_unknown_top_level_key_is_rejected_with_key_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from ask_my_cv.settings import ConfigError

    path = tmp_path / "settings.yaml"
    path.write_text(YAML + "cors_origin: ['https://ok.example']\n", encoding="utf-8")
    monkeypatch.delenv("OLLAMA_URL", raising=False)
    with pytest.raises(ConfigError) as info:
        load_settings(path)
    assert "cors_origin" in str(info.value)
    assert "ok.example" not in str(info.value)


def test_unknown_key_in_model_entry_is_rejected() -> None:
    data = minimal()
    data["models"][0]["unexpected_key"] = "nope"
    with pytest.raises(ValidationError) as info:
        Settings.model_validate(data)
    assert "unexpected_key" in str(info.value)


@pytest.mark.parametrize("dim", [4097, 5000])
def test_embed_dim_upper_bound_is_enforced(dim: int) -> None:
    with pytest.raises(ValidationError):
        Settings.model_validate(minimal(embed_dim=dim))


def test_embed_dim_at_upper_bound_is_accepted() -> None:
    assert Settings.model_validate(minimal(embed_dim=4096)).embed_dim == 4096


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "ftp://host",
        "not-a-url",
        "http://",
        "https://",
    ],
)
def test_ollama_url_rejects_non_http_schemes_or_missing_host(url: str) -> None:
    with pytest.raises(ValidationError):
        Settings.model_validate(minimal(ollama_url=url))


def test_ollama_url_accepts_https_with_host() -> None:
    settings = Settings.model_validate(minimal(ollama_url="https://ollama.internal:11434"))
    assert settings.ollama_url == "https://ollama.internal:11434"


def test_dev_settings_file_loads(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OLLAMA_URL", raising=False)
    monkeypatch.delenv("ASK_ENVIRONMENT", raising=False)
    monkeypatch.delenv("VISITOR_SALT", raising=False)
    settings = load_settings(Path("settings.yaml"))
    assert settings.environment == "dev"
    assert settings.default_model == "ollama:gemma3"


def test_config_error_never_reveals_the_salt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from ask_my_cv.settings import ConfigError

    path = tmp_path / "settings.yaml"
    path.write_text(YAML + "cors_origins: ['*']\n", encoding="utf-8")
    secret = "S3CR3T-" + "q" * 40
    monkeypatch.setenv("ASK_ENVIRONMENT", "prod")
    monkeypatch.setenv("VISITOR_SALT", secret)
    with pytest.raises(ConfigError) as info:
        load_settings(path)
    assert "S3CR3T" not in str(info.value) and "qqqq" not in str(info.value)
    monkeypatch.setenv("VISITOR_SALT", "S3CR3T-court")
    with pytest.raises(ConfigError) as info:
        load_settings(path)
    assert "S3CR3T" not in str(info.value)
