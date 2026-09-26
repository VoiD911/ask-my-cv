from typing import Any

import boto3
import pytest
from botocore.exceptions import ClientError
from moto import mock_aws

from ask_my_cv.secrets import SECRET_NAMES, _ssm_client, apply_ssm_secrets, load_ssm_secrets
from ask_my_cv.settings import ConfigError


@pytest.fixture
def ssm():
    with mock_aws():
        client = boto3.client("ssm", region_name="ca-central-1")
        for name in [*SECRET_NAMES, "AUTRE"]:
            client.put_parameter(
                Name=f"/ask-my-cv/{name}", Value=f"valeur-{name}", Type="SecureString"
            )
        yield client


def test_loads_only_known_secrets(ssm) -> None:
    values = load_ssm_secrets("/ask-my-cv/", ssm)
    assert values == {name: f"valeur-{name}" for name in SECRET_NAMES}


def test_explicit_environment_wins(ssm) -> None:
    env = {"ASK_SSM_PREFIX": "/ask-my-cv/", "VISITOR_SALT": "déjà-là"}
    apply_ssm_secrets(env, client_factory=lambda: ssm)
    assert env["VISITOR_SALT"] == "déjà-là"
    assert env["LANGFUSE_SECRET_KEY"] == "valeur-LANGFUSE_SECRET_KEY"


def test_no_prefix_means_no_aws_call() -> None:
    def boom():
        raise AssertionError("aucun client ne doit être créé")

    env: dict[str, str] = {}
    apply_ssm_secrets(env, client_factory=boom)
    assert env == {}


def test_missing_parameters_are_not_invented(ssm) -> None:
    env = {"ASK_SSM_PREFIX": "/autre-prefixe/"}
    with pytest.raises(ConfigError) as exc_info:
        apply_ssm_secrets(env, client_factory=lambda: ssm)
    assert env == {"ASK_SSM_PREFIX": "/autre-prefixe/"}
    message = str(exc_info.value)
    for name in SECRET_NAMES:
        assert name in message
    assert "valeur-" not in message


def test_ssm_error_propagates() -> None:
    class BoomClient:
        def get_paginator(self, _name: str) -> Any:
            raise ClientError(
                {"Error": {"Code": "InternalServiceError", "Message": "boom"}},
                "GetParametersByPath",
            )

    env = {"ASK_SSM_PREFIX": "/ask-my-cv/"}
    with pytest.raises(ClientError):
        apply_ssm_secrets(env, client_factory=lambda: BoomClient())


def test_pagination_loads_all_secrets() -> None:
    with mock_aws():
        client = boto3.client("ssm", region_name="ca-central-1")
        for name in SECRET_NAMES:
            client.put_parameter(
                Name=f"/ask-my-cv/{name}", Value=f"valeur-{name}", Type="SecureString"
            )
        for i in range(12):
            client.put_parameter(
                Name=f"/ask-my-cv/AUTRE_{i}", Value=f"autre-{i}", Type="SecureString"
            )
        values = load_ssm_secrets("/ask-my-cv/", client)
        assert values == {name: f"valeur-{name}" for name in SECRET_NAMES}


def test_nested_parameters_are_ignored(ssm) -> None:
    ssm.put_parameter(
        Name="/ask-my-cv/x/VISITOR_SALT", Value="ne-doit-pas-etre-lu", Type="SecureString"
    )
    values = load_ssm_secrets("/ask-my-cv/", ssm)
    assert values["VISITOR_SALT"] == "valeur-VISITOR_SALT"


def test_ssm_client_region_falls_back_to_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AWS_REGION", raising=False)
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-west-2")
    client = _ssm_client()
    assert client.meta.region_name == "us-west-2"


def test_optional_eval_token_is_loaded_when_present(ssm) -> None:
    ssm.put_parameter(Name="/ask-my-cv/EVAL_TOKEN", Value="jeton-eval", Type="SecureString")
    env = {"ASK_SSM_PREFIX": "/ask-my-cv/"}
    apply_ssm_secrets(env, client_factory=lambda: ssm)
    assert env["EVAL_TOKEN"] == "jeton-eval"
    assert env["VISITOR_SALT"] == "valeur-VISITOR_SALT"


def test_absent_eval_token_is_not_an_error(ssm) -> None:
    env = {"ASK_SSM_PREFIX": "/ask-my-cv/"}
    apply_ssm_secrets(env, client_factory=lambda: ssm)
    assert "EVAL_TOKEN" not in env
