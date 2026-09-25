import boto3
from botocore.stub import Stubber

from ask_my_cv.aws.dynamo import INDEX_NAME, DynamoVectorStore
from ask_my_cv.vectorstore import Chunk


def item(id: str, section: str, text: str) -> dict:
    return {"id": {"S": id}, "section": {"S": section}, "text": {"S": text}}


async def test_search_sends_a_vector_list_and_maps_results() -> None:
    client = boto3.client("dynamodb", region_name="ca-central-1")
    stub = Stubber(client)
    stub.add_response(
        "search_vectors",
        {
            "SearchResults": [
                {"Item": item("c2", "Compétences", "Python"), "Score": 0.91},
                {"Item": item("c1", "Expérience", "MLOps"), "Score": 0.42},
            ]
        },
        {
            "TableName": "chunks",
            "IndexName": INDEX_NAME,
            "SearchVector": [{"N": "0.5"}, {"N": "-0.25"}],
            "TopK": 2,
        },
    )
    with stub:
        hits = await DynamoVectorStore("chunks", client).search([0.5, -0.25], k=2)
    stub.assert_no_pending_responses()
    assert [(h.chunk.id, h.chunk.section, h.score) for h in hits] == [
        ("c2", "Compétences", 0.91),
        ("c1", "Expérience", 0.42),
    ]


def test_write_puts_chunks_with_their_embedding() -> None:
    client = boto3.client("dynamodb", region_name="ca-central-1")
    stub = Stubber(client)
    stub.add_response(
        "put_item",
        {},
        {
            "TableName": "chunks",
            "Item": {
                **item("c1", "Expérience", "MLOps"),
                "embedding": {"L": [{"N": "0.5"}, {"N": "1.0"}]},
            },
        },
    )
    with stub:
        DynamoVectorStore("chunks", client).write(
            [Chunk("c1", "Expérience", "MLOps")], [[0.5, 1.0]]
        )
    stub.assert_no_pending_responses()
