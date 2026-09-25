from pathlib import Path

from ask_my_cv.vectorstore import Chunk, InMemoryVectorStore

CHUNKS = [
    Chunk(id="c1", section="A", text="alpha"),
    Chunk(id="c2", section="B", text="beta"),
    Chunk(id="c3", section="C", text="gamma"),
]
VECTORS = [[1.0, 0.0], [0.0, 1.0], [0.7, 0.7]]


async def test_search_ranks_by_cosine_and_limits_k() -> None:
    store = InMemoryVectorStore(CHUNKS, VECTORS)
    hits = await store.search([1.0, 0.1], k=2)
    assert [h.chunk.id for h in hits] == ["c1", "c3"]
    assert hits[0].score > hits[1].score


async def test_empty_store_returns_nothing() -> None:
    assert await InMemoryVectorStore([], []).search([1.0, 0.0], k=3) == []


def test_mismatched_lengths_rejected() -> None:
    try:
        InMemoryVectorStore(CHUNKS, VECTORS[:2])
    except ValueError:
        return
    raise AssertionError("ValueError attendu")


async def test_save_load_roundtrip(tmp_path: Path) -> None:
    path = tmp_path / "index.json"
    InMemoryVectorStore(CHUNKS, VECTORS).save(path)
    loaded = InMemoryVectorStore.load(path)
    assert len(loaded) == 3
    hits = await loaded.search([0.0, 1.0], k=1)
    assert hits[0].chunk == CHUNKS[1]
