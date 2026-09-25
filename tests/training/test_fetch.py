from pathlib import Path

import pytest

from ml.fetch import IntegrityError, Source, fetch, load_sources

GOOD = b"contenu"


def make_source(sha256: str) -> Source:
    return Source(
        name="demo",
        url="https://example.invalid/demo.parquet",
        sha256=sha256,
        license="MIT",
        role="train",
        label_column="label",
    )


def test_fetch_writes_verified_file(tmp_path: Path) -> None:
    import hashlib

    sha = hashlib.sha256(GOOD).hexdigest()
    path = fetch(make_source(sha), cache_dir=tmp_path, download=lambda url: GOOD)
    assert path == tmp_path / "demo.parquet"
    assert path.read_bytes() == GOOD


def test_fetch_rejects_tampered_file(tmp_path: Path) -> None:
    with pytest.raises(IntegrityError):
        fetch(make_source("0" * 64), cache_dir=tmp_path, download=lambda url: GOOD)
    assert not (tmp_path / "demo.parquet").exists()


def test_fetch_uses_cache_when_hash_matches(tmp_path: Path) -> None:
    import hashlib

    sha = hashlib.sha256(GOOD).hexdigest()
    (tmp_path / "demo.parquet").write_bytes(GOOD)
    calls: list[str] = []
    fetch(make_source(sha), cache_dir=tmp_path, download=lambda url: calls.append(url) or GOOD)
    assert calls == []


def test_repository_sources_are_pinned() -> None:
    sources = load_sources()
    assert {s.name for s in sources} == {"deepset-train", "deepset-test", "gandalf"}
    for source in sources:
        assert "/resolve/" in source.url and "/resolve/main/" not in source.url
        assert len(source.sha256) == 64
        assert source.license in {"Apache-2.0", "MIT"}
