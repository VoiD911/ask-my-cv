from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import httpx
import yaml

SOURCES_PATH = Path("ml/sources.yaml")
CACHE_DIR = Path("ml/.cache")

Role = Literal["train", "eval_deepset", "eval_gandalf"]


class IntegrityError(Exception):
    """Le fichier téléchargé ne correspond pas au sha256 épinglé."""


@dataclass(frozen=True)
class Source:
    name: str
    url: str
    sha256: str
    license: str
    role: Role
    text_column: str = "text"
    label_column: str | None = None
    fixed_label: int | None = None


def load_sources(path: Path = SOURCES_PATH) -> list[Source]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return [Source(**item) for item in data["sources"]]


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _http_download(url: str) -> bytes:
    response = httpx.get(url, follow_redirects=True, timeout=60)
    response.raise_for_status()
    return response.content


def fetch(
    source: Source,
    cache_dir: Path = CACHE_DIR,
    download: Callable[[str], bytes] = _http_download,
) -> Path:
    target = cache_dir / f"{source.name}.parquet"
    if target.exists() and _sha256(target.read_bytes()) == source.sha256:
        return target
    data = download(source.url)
    digest = _sha256(data)
    if digest != source.sha256:
        raise IntegrityError(f"{source.name} : sha256 {digest} au lieu de {source.sha256}")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    return target


def main() -> None:
    for source in load_sources():
        fetch(source)
        print(f"{source.name} : vérifié ({source.license})")


if __name__ == "__main__":
    main()
