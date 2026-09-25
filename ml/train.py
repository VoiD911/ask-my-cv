from __future__ import annotations

import argparse
import hashlib
import json
import re
from importlib.metadata import version
from pathlib import Path

from skl2onnx import to_onnx
from skl2onnx.common.data_types import StringTensorType
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline, make_pipeline

from ask_my_cv.text import normalize_text
from ml.dataset import (
    ADVERSARIAL_PATH,
    HANDWRITTEN_PATH,
    RECRUITER_EVAL_PATH,
    Datasets,
    Example,
    build_datasets,
    fingerprint,
)
from ml.evaluate import Gates, Report, evaluate, load_gates
from ml.fetch import CACHE_DIR, Source, load_sources

HYPERPARAMS = {
    "analyzer": "char",
    "ngram_range": [2, 5],
    "sublinear_tf": False,
    "min_df": 2,
    "C": 10.0,
    "class_weight": "balanced",
}
VERSION_PATTERN = re.compile(r"^v\d+\.\d+\.\d+$")
LIBRARY_NAMES = ["scikit-learn", "skl2onnx", "onnxruntime", "numpy"]


def library_versions() -> dict[str, str]:
    return {name: version(name) for name in LIBRARY_NAMES}


def build_pipeline() -> Pipeline:
    return make_pipeline(
        TfidfVectorizer(
            analyzer="char",
            ngram_range=(2, 5),
            lowercase=True,
            sublinear_tf=False,
            min_df=2,
        ),
        LogisticRegression(C=10.0, max_iter=3000, class_weight="balanced"),
    )


def fit(examples: list[Example]) -> Pipeline:
    pipe = build_pipeline()
    pipe.fit([normalize_text(e.text) for e in examples], [e.label for e in examples])
    return pipe


def to_onnx_bytes(pipe: Pipeline) -> bytes:
    model = to_onnx(
        pipe,
        initial_types=[("text", StringTensorType([None, 1]))],  # pyright: ignore[reportArgumentType]
        options={id(pipe.steps[-1][1]): {"zipmap": False}},
    )
    # skl2onnx accumule les opsets dans une structure dont l'ordre d'itération dépend de
    # PYTHONHASHSEED : on trie pour obtenir un export déterministe d'un process à l'autre.
    ops = sorted(model.opset_import, key=lambda o: o.domain)  # pyright: ignore[reportAttributeAccessIssue]
    del model.opset_import[:]  # pyright: ignore[reportAttributeAccessIssue]
    model.opset_import.extend(ops)  # pyright: ignore[reportAttributeAccessIssue]
    return model.SerializeToString()  # pyright: ignore[reportAttributeAccessIssue]


def render_model_card(metrics: dict) -> str:
    checks = "\n".join(
        f"| {c['name']} | {c['value']:.4f} | {c['limit']} | {'✅' if c['passed'] else '❌'} |"
        for c in metrics["checks"]
    )
    sources = "\n".join(
        f"- `{s['name']}` — licence {s['license']}, sha256 `{s['sha256']}`"
        for s in metrics["sources"]
    )
    return f"""# Classifieur d'injection de prompt — {metrics["version"]}

Modèle maison de l'assistant « Interroge mon CV » : TF-IDF sur n-grammes de caractères (2 à 5)
et régression logistique, exporté en ONNX (aucun pickle).

- sha256 du modèle : `{metrics["model_sha256"]}`
- empreinte des données d'entraînement : `{metrics["dataset_fingerprint"]}`
- porte d'évaluation : **{"réussie" if metrics["passed"] else "échouée"}**

## Porte d'évaluation

| Contrôle | Valeur | Limite | Résultat |
|---|---|---|---|
{checks}

## Données

{sources}
- `handwritten` — questions de recruteurs et attaques écrites à la main (FR/EN), dans le dépôt.
- Ensemble adverse (`ml/data/adversarial.jsonl`) : évaluation uniquement, jamais vu à \
l'entraînement.
- Jeu du domaine (`ml/data/recruiter_eval.jsonl`) : 50 questions de recruteurs légitimes \
(tutoiement, vouvoiement, 3ᵉ personne, FR/EN), évaluation uniquement.

## Limites connues

- Détecteur lexical : une attaque reformulée sans vocabulaire d'injection peut passer ; le garde-fou
  de sortie reste la seconde ligne de défense.
- Entraîné surtout sur de l'anglais ; le français repose sur les exemples écrits à la main.
- Seuil de décision 0,5, identique à `injection_threshold` dans `settings.yaml`.
- Depuis v1.1.0, le rappel deepset (≈ 0,82) est proche de son seuil (0,80) : compromis choisi pour \
ne pas bloquer les questions légitimes au tutoiement.
"""


def run_training(
    ds: Datasets, version: str, out_dir: Path, gates: Gates, sources: list[Source]
) -> Report:
    pipe = fit(ds.train)
    onnx_bytes = to_onnx_bytes(pipe)
    report = evaluate(pipe, onnx_bytes, ds, gates)

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "model.onnx").write_bytes(onnx_bytes)
    metrics = {
        "version": version,
        "model_sha256": hashlib.sha256(onnx_bytes).hexdigest(),
        "dataset_fingerprint": fingerprint(ds.train),
        "hyperparams": HYPERPARAMS,
        "libraries": library_versions(),
        "sources": [{"name": s.name, "license": s.license, "sha256": s.sha256} for s in sources],
        **report.to_dict(),
    }
    (out_dir / "metrics.json").write_text(
        json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (out_dir / "model_card.md").write_text(render_model_card(metrics), encoding="utf-8")
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Entraîne et évalue le classifieur d'injection.")
    parser.add_argument("--version", required=True, help="ex. v1.0.0")
    parser.add_argument("--out", type=Path, default=Path("dist"))
    args = parser.parse_args(argv)
    if not VERSION_PATTERN.match(args.version):
        parser.error("la version doit ressembler à v1.2.3")

    sources = load_sources()
    ds = build_datasets(sources, CACHE_DIR, HANDWRITTEN_PATH, ADVERSARIAL_PATH, RECRUITER_EVAL_PATH)
    report = run_training(ds, args.version, args.out, load_gates(), sources)
    for check in report.checks:
        status = "OK" if check.passed else "KO"
        print(f"{status}  {check.name} = {check.value:.4f} (limite {check.limit})")
    for text in report.adversarial_failures:
        print(f"KO  adverse : {text}")
    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
