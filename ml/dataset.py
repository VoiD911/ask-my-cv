from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import pyarrow.parquet as pq

from ml.fetch import Source

HANDWRITTEN_PATH = Path("ml/data/handwritten.jsonl")
ADVERSARIAL_PATH = Path("ml/data/adversarial.jsonl")
RECRUITER_EVAL_PATH = Path("ml/data/recruiter_eval.jsonl")


@dataclass(frozen=True)
class Example:
    text: str
    label: int
    source: str


@dataclass(frozen=True)
class AdversarialCase:
    text: str
    expect: Literal["block", "allow"]


@dataclass
class Datasets:
    train: list[Example]
    eval_deepset: list[Example]
    eval_gandalf: list[Example]
    adversarial: list[AdversarialCase]
    eval_domain: list[Example] = field(default_factory=list)


def read_parquet(path: Path, source: Source) -> list[Example]:
    columns = pq.read_table(path).to_pydict()
    texts = columns[source.text_column]
    if source.fixed_label is not None:
        labels = [source.fixed_label] * len(texts)
    elif source.label_column is not None:
        labels = [int(v) for v in columns[source.label_column]]
    else:
        raise ValueError(f"{source.name} : ni label_column ni fixed_label")
    return [
        Example(text=t, label=y, source=source.name) for t, y in zip(texts, labels, strict=True)
    ]


def _jsonl(path: Path) -> list[dict]:
    lines = path.read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines if line.strip()]


def read_jsonl(path: Path, source_name: str) -> list[Example]:
    return [
        Example(text=r["text"], label=int(r["label"]), source=source_name) for r in _jsonl(path)
    ]


def load_adversarial(path: Path) -> list[AdversarialCase]:
    cases = [AdversarialCase(text=r["text"], expect=r["expect"]) for r in _jsonl(path)]
    for case in cases:
        if case.expect not in ("block", "allow"):
            raise ValueError(f"attente inconnue : {case.expect!r}")
    return cases


def build_datasets(
    sources: list[Source], cache_dir: Path, handwritten: Path, adversarial: Path, domain: Path
) -> Datasets:
    by_role: dict[str, list[Example]] = {"train": [], "eval_deepset": [], "eval_gandalf": []}
    for source in sources:
        by_role[source.role].extend(read_parquet(cache_dir / f"{source.name}.parquet", source))
    train = by_role["train"] + read_jsonl(handwritten, "handwritten")
    cases = load_adversarial(adversarial)
    leaked = {c.text for c in cases} & {e.text for e in train}
    if leaked:
        raise ValueError(f"cas adverses présents dans l'entraînement : {sorted(leaked)}")
    domain_examples = read_jsonl(domain, "recruiter_eval")
    domain_leaked = {e.text for e in domain_examples} & {e.text for e in train}
    if domain_leaked:
        raise ValueError(
            f"questions du domaine présentes dans l'entraînement : {sorted(domain_leaked)}"
        )
    return Datasets(train, by_role["eval_deepset"], by_role["eval_gandalf"], cases, domain_examples)


def fingerprint(examples: list[Example]) -> str:
    """Empreinte des données d'entraînement, indépendante de l'ordre."""
    lines = sorted(f"{e.label}\t{e.text}" for e in examples)
    return hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()
