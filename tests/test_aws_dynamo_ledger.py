import boto3
import pytest
from moto import mock_aws

from ask_my_cv.aws.dynamo import DynamoLedger
from ask_my_cv.budget import BudgetExceeded, RateLimited

T0 = 1_790_000_000.0


@pytest.fixture
def ledger():
    with mock_aws():
        client = boto3.client("dynamodb", region_name="ca-central-1")
        client.create_table(
            TableName="ledger",
            BillingMode="PAY_PER_REQUEST",
            KeySchema=[{"AttributeName": "pk", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "pk", "AttributeType": "S"}],
        )
        yield DynamoLedger("ledger", client, daily_cap_usd=0.01, per_visitor_limit=2, window_s=60)


def test_rate_limit_is_atomic_per_fixed_window(ledger: DynamoLedger) -> None:
    ledger.check("v1", T0)
    ledger.check("v1", T0 + 1)
    with pytest.raises(RateLimited):
        ledger.check("v1", T0 + 2)
    ledger.check("v2", T0 + 2)
    ledger.check("v1", T0 + 60 - (T0 % 60) + 1)  # fenêtre suivante


def test_spend_accumulates_per_day_and_provider_then_blocks(ledger: DynamoLedger) -> None:
    ledger.record("bedrock:haiku", 0.006, T0)
    ledger.record("fake:echo", 0.0, T0)
    assert ledger.spent_today(T0) == pytest.approx(0.006)
    ledger.check("v1", T0)
    ledger.record("bedrock:haiku", 0.006, T0)
    assert ledger.spent_by_provider(T0) == {"bedrock:haiku": pytest.approx(0.012), "fake:echo": 0.0}
    with pytest.raises(BudgetExceeded):
        ledger.check("v1", T0)
    assert ledger.spent_today(T0 + 86_400) == 0.0


def test_check_returns_todays_spend_with_a_single_read(ledger: DynamoLedger) -> None:
    reads: list[str] = []
    ledger._client.meta.events.register(
        "before-call.dynamodb.GetItem", lambda **_: reads.append("GetItem")
    )
    ledger.record("p", 0.0025, T0)
    assert ledger.check("v1", T0) == pytest.approx(0.0025)
    assert reads == ["GetItem"]


def test_items_carry_a_ttl(ledger: DynamoLedger) -> None:
    ledger.check("v1", T0)
    ledger.record("p", 0.001, T0)
    items = ledger._client.scan(TableName="ledger")["Items"]
    assert all(int(i["expires_at"]["N"]) > T0 for i in items)
