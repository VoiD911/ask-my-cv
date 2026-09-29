from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import onnxruntime as ort
import yaml
from sklearn.pipeline import Pipeline

from ask_my_cv.onnx_detector import score_texts, window_params
from ask_my_cv.text import injection_windows
from ml.dataset import Datasets

GATES_PATH = Path("ml/gates.yaml")
BINS = [round(i / 10, 1) for i in range(11)]
# Tranches de longueur (caractères) des annonces : le max sur les fenêtres fait croître le risque
# de faux positif avec le nombre de fenêtres, on suit donc le FPR par tranche.
LENGTH_BUCKETS = ((0, 1_500), (1_500, 4_000), (4_000, 7_000), (7_000, 1_000_000))


@dataclass(frozen=True)
class Gates:
    threshold: float = 0.5
    deepset_min_recall: float = 0.80
    deepset_max_fpr: float = 0.05
    gandalf_min_recall: float = 0.95
    domain_max_fpr: float = 0.0
    job_ad_max_fpr: float = 0.0
    job_ad_min_recall: float = 0.90
    parity_max_diff: float = 0.001


def load_gates(path: Path = GATES_PATH) -> Gates:
    return Gates(**yaml.safe_load(path.read_text(encoding="utf-8")))


@dataclass(frozen=True)
class Check:
    name: str
    value: float
    limit: float
    passed: bool


@dataclass
class Report:
    checks: list[Check]
    adversarial_failures: list[str] = field(default_factory=list)
    histogram_counts: list[int] = field(default_factory=list)
    domain_histogram_counts: list[int] = field(default_factory=list)
    domain_question_histogram_counts: list[int] = field(default_factory=list)
    job_ad_histogram_counts: list[int] = field(default_factory=list)
    metrics: dict[str, float] = field(default_factory=dict)
    job_ad_fpr_by_length: list[dict[str, float]] = field(default_factory=list)
    window: tuple[int, int] = (0, 0)

    @property
    def passed(self) -> bool:
        return all(c.passed for c in self.checks)

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "window": {"size": self.window[0], "overlap": self.window[1], "aggregation": "max"},
            "metrics": self.metrics,
            "job_ad_fpr_by_length": self.job_ad_fpr_by_length,
            "checks": [asdict(c) for c in self.checks],
            "adversarial_failures": self.adversarial_failures,
            "score_histogram": {"bins": BINS, "counts": self.histogram_counts},
            # Référence de la dérive (`ml.drift`) : trafic légitime tel que servi, soit les
            # questions du domaine et les annonces légitimes d'évaluation (max sur les fenêtres).
            # Les deux composantes sont aussi publiées séparément.
            "domain_score_histogram": {"bins": BINS, "counts": self.domain_histogram_counts},
            "domain_question_score_histogram": {
                "bins": BINS,
                "counts": self.domain_question_histogram_counts,
            },
            "job_ad_score_histogram": {"bins": BINS, "counts": self.job_ad_histogram_counts},
        }


def onnx_scores(onnx_bytes: bytes, texts: list[str]) -> np.ndarray:
    """Probabilité d'injection selon le modèle ONNX, calculée exactement comme au service."""
    session = ort.InferenceSession(onnx_bytes, providers=["CPUExecutionProvider"])
    return np.asarray(score_texts(session, texts), dtype=float)


def sklearn_scores(pipe: Pipeline, texts: list[str], window: tuple[int, int]) -> np.ndarray:
    """Même calcul que le service, avec le modèle scikit-learn (référence de parité)."""
    groups = [injection_windows(text, *window) for text in texts]
    windows = [w for group in groups for w in group]
    if not windows:
        return np.zeros(0)
    window_scores = pipe.predict_proba(windows)[:, 1]
    result = []
    offset = 0
    for group in groups:
        result.append(float(window_scores[offset : offset + len(group)].max()))
        offset += len(group)
    return np.asarray(result)


def _recall_fpr(scores: np.ndarray, labels: list[int], threshold: float) -> tuple[float, float]:
    if not labels:
        return 0.0, 0.0
    predicted = scores >= threshold
    truth = np.asarray(labels) == 1
    recall = float(predicted[truth].mean()) if truth.any() else 1.0
    fpr = float(predicted[~truth].mean()) if (~truth).any() else 0.0
    return recall, fpr


def _histogram(scores: np.ndarray) -> list[int]:
    counts, _ = np.histogram(scores, bins=10, range=(0.0, 1.0))
    return [int(c) for c in counts]


def _fpr_by_length(texts: list[str], scores: np.ndarray, threshold: float) -> list[dict]:
    rows = []
    for low, high in LENGTH_BUCKETS:
        in_bucket = np.asarray([low <= len(t) < high for t in texts], dtype=bool)
        n = int(in_bucket.sum())
        fpr = float((scores[in_bucket] >= threshold).mean()) if n else 0.0
        max_score = float(scores[in_bucket].max()) if n else 0.0
        rows.append({"min_chars": low, "max_chars": high, "n": n, "fpr": fpr, "max": max_score})
    return rows


def eval_texts(ds: Datasets) -> dict[str, list[str]]:
    """Textes des jeux d'évaluation, dans l'ordre utilisé pour le lot de scores."""
    return {
        "deepset": [e.text for e in ds.eval_deepset],
        "gandalf": [e.text for e in ds.eval_gandalf],
        "adversarial": [c.text for c in ds.adversarial],
        "domain": [e.text for e in ds.eval_domain],
        "job_ads": [e.text for e in ds.eval_job_ads],
    }


def split_scores(sets: dict[str, list[str]], scores: np.ndarray) -> dict[str, np.ndarray]:
    result: dict[str, np.ndarray] = {}
    offset = 0
    for name, group in sets.items():
        result[name] = scores[offset : offset + len(group)]
        offset += len(group)
    return result


@dataclass(frozen=True)
class Measured:
    """Métriques d'un modèle sur les jeux d'évaluation, à partir de ses scores servis."""

    metrics: dict[str, float]
    failures: list[str]
    domain: np.ndarray
    legit_ads: np.ndarray
    deepset: np.ndarray


def measure(ds: Datasets, scores: dict[str, np.ndarray], threshold: float) -> Measured:
    t = threshold
    recall, fpr = _recall_fpr(scores["deepset"], [e.label for e in ds.eval_deepset], t)
    gand = scores["gandalf"]
    gand_recall = float((gand >= t).mean()) if len(gand) else 0.0
    domain = scores["domain"]
    domain_fpr = float((domain >= t).mean()) if len(domain) else 1.0
    ad_labels = np.asarray([e.label for e in ds.eval_job_ads], dtype=int)
    ad_scores = scores["job_ads"]
    legit_ads, injected_ads = ad_scores[ad_labels == 0], ad_scores[ad_labels == 1]
    ad_fpr = float((legit_ads >= t).mean()) if len(legit_ads) else 1.0
    ad_recall = float((injected_ads >= t).mean()) if len(injected_ads) else 0.0
    failures = [
        case.text
        for case, score in zip(ds.adversarial, scores["adversarial"], strict=True)
        if (score >= t) != (case.expect == "block")
    ]
    adv_rate = 1.0 - len(failures) / len(ds.adversarial) if ds.adversarial else 1.0
    metrics = {
        "deepset_recall": recall,
        "deepset_fpr": fpr,
        "gandalf_recall": gand_recall,
        "domain_fpr": domain_fpr,
        "domain_max_score": float(domain.max()) if len(domain) else 0.0,
        "job_ad_fpr": ad_fpr,
        "job_ad_recall": ad_recall,
        "job_ad_legit_max_score": float(legit_ads.max()) if len(legit_ads) else 0.0,
        "adversarial_pass_rate": adv_rate,
        "n_deepset": len(scores["deepset"]),
        "n_gandalf": len(gand),
        "n_domain": len(domain),
        "n_job_ads_legit": len(legit_ads),
        "n_job_ads_injected": len(injected_ads),
        "n_train_removed_near_duplicates": ds.removed_near_duplicates,
    }
    return Measured(metrics, failures, domain, legit_ads, scores["deepset"])


def evaluate(pipe: Pipeline, onnx_bytes: bytes, ds: Datasets, gates: Gates) -> Report:
    session = ort.InferenceSession(onnx_bytes, providers=["CPUExecutionProvider"])
    window = window_params(session)
    sets = eval_texts(ds)
    texts = [t for group in sets.values() for t in group]
    served = np.asarray(score_texts(session, texts), dtype=float)
    reference = sklearn_scores(pipe, texts, window)
    parity = float(np.max(np.abs(served - reference))) if texts else 0.0
    same_decisions = bool(np.array_equal(served >= gates.threshold, reference >= gates.threshold))

    m = measure(ds, split_scores(sets, served), gates.threshold)
    v = m.metrics

    def at_least(name: str, limit: float, non_empty: bool = True) -> Check:
        return Check(name, v[name], limit, v[name] >= limit and non_empty)

    def at_most(name: str, limit: float, non_empty: bool = True) -> Check:
        return Check(name, v[name], limit, v[name] <= limit and non_empty)

    checks = [
        at_least("deepset_recall", gates.deepset_min_recall),
        at_most("deepset_fpr", gates.deepset_max_fpr),
        at_least("gandalf_recall", gates.gandalf_min_recall),
        at_most("domain_fpr", gates.domain_max_fpr, len(m.domain) > 0),
        at_most("job_ad_fpr", gates.job_ad_max_fpr, len(m.legit_ads) > 0),
        at_least("job_ad_recall", gates.job_ad_min_recall, v["n_job_ads_injected"] > 0),
        Check("adversarial_pass_rate", v["adversarial_pass_rate"], 1.0, not m.failures),
        Check(
            "onnx_parity_max_diff",
            parity,
            gates.parity_max_diff,
            parity <= gates.parity_max_diff and same_decisions,
        ),
    ]
    legit_ad_texts = [e.text for e in ds.eval_job_ads if e.label == 0]
    # `ml.drift` écarte les scores de production au-dessus du seuil : la référence aussi
    legit = np.concatenate([m.domain, m.legit_ads])
    return Report(
        checks=checks,
        adversarial_failures=m.failures,
        histogram_counts=_histogram(m.deepset),
        domain_histogram_counts=_histogram(legit[legit < gates.threshold]),
        domain_question_histogram_counts=_histogram(m.domain),
        job_ad_histogram_counts=_histogram(m.legit_ads),
        metrics=v,
        job_ad_fpr_by_length=_fpr_by_length(legit_ad_texts, m.legit_ads, gates.threshold),
        window=window,
    )
