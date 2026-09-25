import boto3


def test_boto3_clients_are_isolated() -> None:
    client = boto3.client("dynamodb", region_name="ca-central-1")
    assert "SearchVectors" in client.meta.service_model.operation_names
    assert client._request_signer._credentials.access_key == "testing"
