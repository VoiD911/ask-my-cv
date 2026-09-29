"""Compare des modèles ONNX sur les mêmes jeux d'évaluation et le même mode d'inférence.

python -m ml.compare --model v1.3.0=chemin/model.onnx --model candidat=dist/model.onnx \
    [--whole v1.2.0] [--text annonce=chemin/annonce.txt ...]

Chaque modèle est scoré comme au service (fenêtres de ses métadonnées, 600/120 s'il n'en a pas,
maximum). `--whole NOM` ajoute une colonne « NOM (texte entier) » qui score le texte normalisé
d'un seul tenant, le mode d'avant v1.3.0. `--text` ajoute le score de textes libres (fixtures des
évaluations de nuit, par exemple). Sortie : tableaux Markdown sur la sortie standard.
"""

from __future__ import annotations

import argparse
from collections.abc import Callable
from pathlib import Path

import numpy as np
import onnxruntime as ort

from ask_my_cv.onnx_detector import normalization_version, score_texts
from ask_my_cv.text import normalize_text
from ml.evaluate import eval_texts, load_gates, measure, split_scores
from ml.train import load_repository_datasets

Scorer = Callable[[list[str]], np.ndarray]
ROWS = (
    "deepset_recall",
    "deepset_fpr",
    "gandalf_recall",
    "domain_fpr",
    "domain_max_score",
    "job_ad_fpr",
    "job_ad_recall",
    "job_ad_legit_max_score",
    "adversarial_pass_rate",
)


def served_scorer(session: ort.InferenceSession) -> Scorer:
    return lambda texts: np.asarray(score_texts(session, texts), dtype=float)


def whole_text_scorer(session: ort.InferenceSession) -> Scorer:
    def score(texts: list[str]) -> np.ndarray:
        if not texts:
            return np.zeros(0)
        version = normalization_version(session)
        batch = [normalize_text(t, version) for t in texts]
        batch = np.asarray(batch, dtype=object).reshape(-1, 1)
        return np.asarray(session.run(None, {"text": batch})[1])[:, 1].astype(float)

    return score


def _spec(value: str) -> tuple[str, str]:
    name, sep, rest = value.partition("=")
    if not sep or not name or not rest:
        raise argparse.ArgumentTypeError(f"attendu NOM=CHEMIN : {value!r}")
    return name, rest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", type=_spec, action="append", required=True)
    parser.add_argument("--whole", action="append", default=[])
    parser.add_argument("--text", type=_spec, action="append", default=[])
    args = parser.parse_args(argv)

    scorers: dict[str, Scorer] = {}
    for name, path in args.model:
        session = ort.InferenceSession(Path(path).read_bytes(), providers=["CPUExecutionProvider"])
        if name in args.whole:
            scorers[f"{name} (texte entier)"] = whole_text_scorer(session)
        scorers[name] = served_scorer(session)

    ds, _ = load_repository_datasets()
    threshold = load_gates().threshold
    sets = eval_texts(ds)
    texts = [t for group in sets.values() for t in group]
    extra = {name: Path(path).read_text(encoding="utf-8") for name, path in args.text}

    columns = {}
    free = {}
    for name, scorer in scorers.items():
        columns[name] = measure(ds, split_scores(sets, scorer(texts)), threshold).metrics
        free[name] = scorer(list(extra.values()))

    header = "| Métrique | " + " | ".join(scorers) + " |"
    rule = "|---|" + "---|" * len(scorers)
    print(header, rule, sep="\n")
    for row in ROWS:
        print(f"| {row} | " + " | ".join(f"{columns[n][row]:.4f}" for n in scorers) + " |")
    counts = columns[next(iter(scorers))]
    print(
        f"\nEffectifs : deepset {counts['n_deepset']}, gandalf {counts['n_gandalf']}, domaine "
        f"{counts['n_domain']}, annonces {counts['n_job_ads_legit']} légitimes / "
        f"{counts['n_job_ads_injected']} injectées ; seuil {threshold}."
    )
    if extra:
        print("\n| Texte | caractères | " + " | ".join(scorers) + " |")
        print("|---|---|" + "---|" * len(scorers))
        for i, (name, text) in enumerate(extra.items()):
            cells = " | ".join(f"{free[n][i]:.4f}" for n in scorers)
            print(f"| {name} | {len(text)} | {cells} |")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
