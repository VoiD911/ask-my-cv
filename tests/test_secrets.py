import boto3
import pytest
from moto import mock_aws

from ask_my_cv.secrets import SECRET_NAMES, apply_ssm_secrets, load_ssm_secrets


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
    apply_ssm_secrets(env, client_factory=lambda: ssm)
    assert env == {"ASK_SSM_PREFIX": "/autre-prefixe/"}
