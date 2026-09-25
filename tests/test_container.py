from ask_my_cv.aws.bedrock import BedrockEmbedder, BedrockLLM
from ask_my_cv.aws.dynamo import DynamoLedger, DynamoVectorStore
from ask_my_cv.container import (
    aws_client,
    build_embedder,
    build_ledger,
    build_provider,
    build_store,
)
from ask_my_cv.settings import ModelConfig, Settings


def aws_settings() -> Settings:
    return Settings(
        models=[
            ModelConfig(
                id="bedrock:h",
                provider="bedrock",
                model="us.anthropic.claude-haiku-4-5-20251001-v1:0",
            )
        ],
        default_model="bedrock:h",
        fallback_chain=["bedrock:h"],
        embedder="bedrock",
        embed_dim=1024,
        vector_store="dynamodb",
        ledger="dynamodb",
    )


def test_aws_settings_build_aws_adapters_without_network() -> None:
    s = aws_settings()
    assert isinstance(build_provider(s.models[0], s), BedrockLLM)
    assert isinstance(build_embedder(s), BedrockEmbedder)
    assert isinstance(build_store(s), DynamoVectorStore)
    assert isinstance(build_ledger(s), DynamoLedger)


def test_dynamodb_client_has_short_timeouts() -> None:
    config = aws_client("dynamodb", aws_settings()).meta.config
    assert (config.connect_timeout, config.read_timeout) == (2, 3)


def test_bedrock_runtime_client_has_a_generous_read_timeout() -> None:
    config = aws_client("bedrock-runtime", aws_settings()).meta.config
    assert (config.connect_timeout, config.read_timeout) == (3, 30)
