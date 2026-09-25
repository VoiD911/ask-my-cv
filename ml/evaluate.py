from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import onnxruntime as ort
import yaml
from sklearn.pipeline import Pipeline

from ml.dataset import Datasets

GATES_PATH = Path("ml/gates.yaml")


@dataclass(frozen=True)
class Gates:
    threshold: float = 0.5
    deepset_min_recall: float = 0.80
    deepset_max_fpr: float = 0.05
    gandalf_min_recall: float = 0.95
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

    @property
    def passed(self) -> bool:
        return all(c.passed for c in self.checks)

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "checks": [asdict(c) for c in self.checks],
            "adversarial_failures": self.adversarial_failures,
            "score_histogram": {
                "bins": [round(i / 10, 1) for i in range(11)],
                "counts": self.histogram_counts,
            },
        }


def onnx_scores(onnx_bytes: bytes, texts: list[str]) -> np.ndarray:
    """Probabilité d'injection selon le modèle ONNX, celui qui est réellement servi."""
    if not texts:
        return np.zeros(0)
    session = ort.InferenceSession(onnx_bytes, providers=["CPUExecutionProvider"])
    outputs = session.run(None, {"text": np.array(texts, dtype=object).reshape(-1, 1)})
    return np.asarray(outputs[1])[:, 1]


def _recall_fpr(scores: np.ndarray, labels: list[int], threshold: float) -> tuple[float, float]:
    predicted = scores >= threshold
    truth = np.asarray(labels) == 1
    recall = float(predicted[truth].mean()) if truth.any() else 1.0
    fpr = float(predicted[~truth].mean()) if (~truth).any() else 0.0
    return recall, fpr


def evaluate(pipe: Pipeline, onnx_bytes: bytes, ds: Datasets, gates: Gates) -> Report:
    deepset = [e.text for e in ds.eval_deepset]
    gandalf = [e.text for e in ds.eval_gandalf]
    adversarial = [c.text for c in ds.adversarial]
    texts = deepset + gandalf + adversarial

    served = onnx_scores(onnx_bytes, texts)
    reference = pipe.predict_proba(texts)[:, 1] if texts else np.zeros(0)
    parity = float(np.max(np.abs(served - reference))) if texts else 0.0
    same_decisions = bool(np.array_equal(served >= gates.threshold, reference >= gates.threshold))

    n_deep, n_gand = len(deepset), len(gandalf)
    deep_scores = served[:n_deep]
    gand_scores = served[n_deep : n_deep + n_gand]
    adv_scores = served[n_deep + n_gand :]

    recall, fpr = _recall_fpr(deep_scores, [e.label for e in ds.eval_deepset], gates.threshold)
    gand_recall = float((gand_scores >= gates.threshold).mean()) if n_gand else 1.0
    failures = [
        case.text
        for case, score in zip(ds.adversarial, adv_scores, strict=True)
        if (score >= gates.threshold) != (case.expect == "block")
    ]
    adv_rate = 1.0 - len(failures) / len(ds.adversarial) if ds.adversarial else 1.0

    checks = [
        Check(
            "deepset_recall", recall, gates.deepset_min_recall, recall >= gates.deepset_min_recall
        ),
        Check("deepset_fpr", fpr, gates.deepset_max_fpr, fpr <= gates.deepset_max_fpr),
        Check(
            "gandalf_recall",
            gand_recall,
            gates.gandalf_min_recall,
            gand_recall >= gates.gandalf_min_recall,
        ),
        Check("adversarial_pass_rate", adv_rate, 1.0, not failures),
        Check(
            "onnx_parity_max_diff",
            parity,
            gates.parity_max_diff,
            parity <= gates.parity_max_diff and same_decisions,
        ),
    ]
    counts, _ = np.histogram(deep_scores, bins=10, range=(0.0, 1.0))
    return Report(checks, failures, [int(c) for c in counts])
