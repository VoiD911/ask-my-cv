from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import numpy as np
import pyarrow.parquet as pq
from scipy.sparse import csr_matrix

from ask_my_cv.text import WINDOW_OVERLAP, WINDOW_SIZE, normalize_text, window_starts
from ml.fetch import Source

HANDWRITTEN_PATH = Path("ml/data/handwritten.jsonl")
JOB_ADS_TRAIN_PATH = Path("ml/data/job_ads_train.jsonl")
ADVERSARIAL_PATH = Path("ml/data/adversarial.jsonl")
RECRUITER_EVAL_PATH = Path("ml/data/recruiter_eval.jsonl")
JOB_ADS_EVAL_PATH = Path("ml/data/job_ads_eval.jsonl")

# Au-delà de ce Jaccard (ensembles de mots normalisés), deux textes sont des quasi-doublons : une
# ligne d'entraînement reformule un cas d'évaluation, et la porte mesurerait la mémorisation au
# lieu de la généralisation. Seuil repris de la revue de #101.
NEAR_DUPLICATE_JACCARD = 0.5
# À l'intérieur d'un même jeu d'annonces, le vocabulaire commun de deux longues annonces gonfle le
# Jaccard de mots sans qu'elles se copient : on y mesure les tournures (4-grammes de mots, la
# mesure de la revue de #101), au même seuil.
AD_SHINGLE_NGRAM = 4


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
    eval_job_ads: list[Example] = field(default_factory=list)
    # lignes de sources publiques retirées de l'entraînement car quasi-doublons d'une évaluation
    removed_near_duplicates: int = 0


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


@dataclass(frozen=True)
class JobAdRow:
    text: str
    label: int
    injection: str | None


def read_job_ads(path: Path) -> list[JobAdRow]:
    rows = [JobAdRow(r["text"], int(r["label"]), r.get("injection")) for r in _jsonl(path)]
    for row in rows:
        if (row.label == 1) != (row.injection is not None):
            raise ValueError(f"{path} : une annonce injectée doit indiquer son injection")
    return rows


def ad_windows(
    row: JobAdRow, source: str, size: int = WINDOW_SIZE, overlap: int = WINDOW_OVERLAP
) -> list[Example]:
    """Exemples d'entraînement d'une annonce, découpée comme au service.

    Une fenêtre est étiquetée 1 si elle contient toute l'injection, 0 si elle n'en contient rien ;
    une fenêtre qui n'en voit qu'un morceau est écartée (étiquette ambiguë).
    """
    text = normalize_text(row.text)
    span: tuple[int, int] | None = None
    if row.injection is not None:
        injection = normalize_text(row.injection)
        start = text.find(injection)
        if start < 0:
            raise ValueError(f"injection absente du texte de l'annonce : {row.injection!r}")
        span = (start, start + len(injection))
    examples = []
    for start in window_starts(len(text), size, overlap):
        end = start + size
        window = text[start:end]
        if span is None or span[1] <= start or span[0] >= end:
            examples.append(Example(window, 0, source))
        elif start <= span[0] and span[1] <= end:
            examples.append(Example(window, 1, source))
    return examples


def _words(text: str) -> list[str]:
    """Minuscules, sans accents ni ponctuation, espaces fusionnés."""
    folded = unicodedata.normalize("NFKD", text.lower())
    folded = "".join(c for c in folded if not unicodedata.combining(c))
    return re.sub(r"[^\w\s]", " ", folded).split()


def _tokens(text: str, ngram: int = 1) -> frozenset[str]:
    """Ensemble des n-grammes de mots (n = 1 : vocabulaire ; n = 4 : tournures de phrase).

    Un texte de moins de `ngram` mots donne un seul n-gramme, le texte entier.
    """
    words = _words(text)
    if ngram == 1 or len(words) < ngram:
        return frozenset([" ".join(words)] if ngram > 1 and words else words)
    return frozenset(" ".join(words[i : i + ngram]) for i in range(len(words) - ngram + 1))


def _jaccard_sets(a: frozenset[str], b: frozenset[str]) -> float:
    union = len(a | b)
    return len(a & b) / union if union else 1.0


def jaccard(a: str, b: str, ngram: int = 1) -> float:
    return _jaccard_sets(_tokens(a, ngram), _tokens(b, ngram))


def near_duplicate_pairs(
    left: list[str], right: list[str], threshold: float = NEAR_DUPLICATE_JACCARD, ngram: int = 1
) -> list[tuple[int, int, float]]:
    """Paires (i, j, jaccard) avec jaccard(left[i], right[j], ngram) ≥ seuil, par produit creux."""
    if not left or not right:
        return []
    vocab: dict[str, int] = {}
    sets = ([_tokens(t, ngram) for t in left], [_tokens(t, ngram) for t in right])
    matrices = []
    for token_sets in sets:
        rows, cols = [], []
        for i, tokens in enumerate(token_sets):
            for token in tokens:
                rows.append(i)
                cols.append(vocab.setdefault(token, len(vocab)))
        matrices.append((rows, cols, len(token_sets)))
    a, b = (
        csr_matrix((np.ones(len(r), dtype=np.int32), (r, c)), shape=(n, len(vocab)))
        for r, c, n in matrices
    )
    inter = (a @ b.T).tocoo()
    size_a = np.asarray(a.sum(axis=1)).ravel()
    size_b = np.asarray(b.sum(axis=1)).ravel()
    scores = inter.data / (size_a[inter.row] + size_b[inter.col] - inter.data)
    keep = scores >= threshold
    pairs = [
        (int(i), int(j), float(s))
        for i, j, s in zip(inter.row[keep], inter.col[keep], scores[keep], strict=True)
    ]
    # deux textes sans aucun mot : Jaccard 1 par convention (absents du produit creux)
    empty_right = [j for j, tokens in enumerate(sets[1]) if not tokens]
    pairs.extend((i, j, 1.0) for i, t in enumerate(sets[0]) if not t for j in empty_right)
    return pairs


class Deduplicator:
    """Accepte un texte seulement s'il n'est quasi-doublon d'aucun texte déjà accepté."""

    def __init__(self, threshold: float = NEAR_DUPLICATE_JACCARD, ngram: int = 1) -> None:
        self.threshold = threshold
        self.ngram = ngram
        self._kept: list[frozenset[str]] = []

    def add(self, text: str) -> bool:
        tokens = _tokens(text, self.ngram)
        if any(_jaccard_sets(tokens, other) >= self.threshold for other in self._kept):
            return False
        self._kept.append(tokens)
        return True


def load_adversarial(path: Path) -> list[AdversarialCase]:
    cases = [AdversarialCase(text=r["text"], expect=r["expect"]) for r in _jsonl(path)]
    for case in cases:
        if case.expect not in ("block", "allow"):
            raise ValueError(f"attente inconnue : {case.expect!r}")
    return cases


def build_datasets(
    sources: list[Source],
    cache_dir: Path,
    handwritten: Path,
    adversarial: Path,
    domain: Path,
    job_ads_train: Path | None = None,
    job_ads_eval: Path | None = None,
) -> Datasets:
    """Assemble les jeux et refuse toute fuite de l'entraînement vers l'évaluation.

    Fichiers du dépôt (écrits à la main ou générés) : un quasi-doublon d'un cas d'évaluation fait
    échouer la construction ; on corrige les données. Sources publiques d'entraînement (non
    modifiables) : la ligne est retirée et comptée dans `removed_near_duplicates`.
    """
    by_role: dict[str, list[Example]] = {"train": [], "eval_deepset": [], "eval_gandalf": []}
    for source in sources:
        by_role[source.role].extend(read_parquet(cache_dir / f"{source.name}.parquet", source))
    cases = load_adversarial(adversarial)
    domain_examples = read_jsonl(domain, "recruiter_eval")
    ads_train = read_job_ads(job_ads_train) if job_ads_train is not None else []
    ads_eval = read_job_ads(job_ads_eval) if job_ads_eval is not None else []
    eval_job_ads = [Example(r.text, r.label, "job_ads_eval") for r in ads_eval]
    held_out = {
        "cas deepset": [e.text for e in by_role["eval_deepset"]],
        "cas gandalf": [e.text for e in by_role["eval_gandalf"]],
        "cas adverses": [c.text for c in cases],
        "questions du domaine": [e.text for e in domain_examples],
        "annonces d'évaluation": [e.text for e in eval_job_ads],
    }

    handwritten_rows = read_jsonl(handwritten, "handwritten")
    repo_texts = [e.text for e in handwritten_rows] + [r.text for r in ads_train]
    for name, texts in held_out.items():
        pairs = near_duplicate_pairs(repo_texts, texts)
        if pairs:
            found = sorted({(round(s, 2), repo_texts[i][:80], texts[j][:80]) for i, j, s in pairs})
            raise ValueError(f"{name} présents (quasi-doublons) dans l'entraînement : {found}")

    held_out_texts = [t for texts in held_out.values() for t in texts]
    public = by_role["train"]
    leaking = {i for i, _, _ in near_duplicate_pairs([e.text for e in public], held_out_texts)}
    train = (
        [e for i, e in enumerate(public) if i not in leaking]
        + handwritten_rows
        + [w for row in ads_train for w in ad_windows(row, "job_ads_train")]
    )
    return Datasets(
        train,
        by_role["eval_deepset"],
        by_role["eval_gandalf"],
        cases,
        domain_examples,
        eval_job_ads,
        len(leaking),
    )


def fingerprint(examples: list[Example]) -> str:
    """Empreinte des données d'entraînement, indépendante de l'ordre."""
    lines = sorted(f"{e.label}\t{e.text}" for e in examples)
    return hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()
