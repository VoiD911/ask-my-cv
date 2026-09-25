import numpy as np

from ask_my_cv.embeddings import HashEmbedder


async def test_hash_embedder_is_deterministic_and_normalized() -> None:
    embedder = HashEmbedder(dim=32)
    [a, b, empty] = await embedder.embed(["MLOps Python", "MLOps Python", ""])
    assert a == b
    assert len(a) == 32
    assert abs(float(np.linalg.norm(a)) - 1.0) < 1e-9
    assert all(v == 0.0 for v in empty)


async def test_hash_embedder_similar_texts_are_closer() -> None:
    embedder = HashEmbedder(dim=256)
    [q, near, far] = await embedder.embed(
        ["compétences Python", "Python FastAPI compétences", "randonnée montagne"]
    )
    assert float(np.dot(q, near)) > float(np.dot(q, far))
