from __future__ import annotations

import argparse
import hashlib
import json
import re
from importlib.metadata import version
from pathlib import Path

import numpy as np
from skl2onnx import to_onnx
from skl2onnx.common.data_types import StringTensorType
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline, make_pipeline, make_union

from ask_my_cv.onnx_detector import META_WINDOW_OVERLAP, META_WINDOW_SIZE
from ask_my_cv.text import WINDOW_OVERLAP, WINDOW_SIZE, injection_windows, normalize_text
from ml.dataset import (
    ADVERSARIAL_PATH,
    HANDWRITTEN_PATH,
    JOB_ADS_EVAL_PATH,
    JOB_ADS_TRAIN_PATH,
    RECRUITER_EVAL_PATH,
    Datasets,
    Example,
    build_datasets,
    fingerprint,
)
from ml.evaluate import Gates, Report, evaluate, load_gates
from ml.fetch import CACHE_DIR, Source, load_sources

# Mesurés le 2026-09-29 (tâche 4b, `ml.compare`) : l'union caractères + mots et la pondération
# remplacent « balanced », qui donnait 0,5 de score a priori à toute prose jamais vue et bloquait
# les annonces légitimes longues. Les questions écrites à la main (proches du trafic réel)
# pèsent 4. Pas de sublinear_tf : l'export ONNX s'écarte alors de 0,001 sur les longs textes.
# Motif de mots explicite : le \w du motif par défaut de scikit-learn est Unicode, celui de re2
# (Tokenizer ONNX) est ASCII ; « expérience » y devient « exp » + « rience » (écart de 0,1 mesuré).
WORD_REGEX = "[0-9A-Za-zÀ-ÖØ-öø-ÿŒœ]{2,}"
HYPERPARAMS = {
    "features": [
        {"analyzer": "char", "ngram_range": [2, 5], "min_df": 2, "sublinear_tf": False},
        {
            "analyzer": "word",
            "ngram_range": [1, 2],
            "min_df": 2,
            "sublinear_tf": False,
            "token_pattern": WORD_REGEX,
        },
    ],
    "C": 3.0,
    "class_weight": {"0": 1.0, "1": 3.0},
    "sample_weight": {"handwritten": 4.0},
}
VERSION_PATTERN = re.compile(r"^v\d+\.\d+\.\d+$")
LIBRARY_NAMES = ["scikit-learn", "skl2onnx", "onnxruntime", "numpy"]


def library_versions() -> dict[str, str]:
    return {name: version(name) for name in LIBRARY_NAMES}


def build_pipeline() -> Pipeline:
    vectorizers = [
        TfidfVectorizer(
            analyzer=f["analyzer"],
            ngram_range=tuple(f["ngram_range"]),
            lowercase=True,
            sublinear_tf=f["sublinear_tf"],
            min_df=f["min_df"],
            **({"token_pattern": f["token_pattern"]} if "token_pattern" in f else {}),
        )
        for f in HYPERPARAMS["features"]
    ]
    weights = {int(k): v for k, v in HYPERPARAMS["class_weight"].items()}
    return make_pipeline(
        make_union(*vectorizers),
        LogisticRegression(C=HYPERPARAMS["C"], max_iter=5000, class_weight=weights),
    )


def sample_weights(examples: list[Example]) -> np.ndarray:
    by_source = HYPERPARAMS["sample_weight"]
    return np.asarray([by_source.get(e.source, 1.0) for e in examples], dtype=float)


def fit(examples: list[Example]) -> Pipeline:
    pipe = build_pipeline()
    pipe.fit(
        [normalize_text(e.text) for e in examples],
        [e.label for e in examples],
        logisticregression__sample_weight=sample_weights(examples),
    )
    return pipe


def to_onnx_bytes(pipe: Pipeline, window: tuple[int, int] = (WINDOW_SIZE, WINDOW_OVERLAP)) -> bytes:
    """Export ONNX déterministe, avec le découpage en fenêtres que le service doit appliquer."""
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
    injection_windows("", *window)  # refuse un découpage invalide avant de l'enregistrer
    for key, value in ((META_WINDOW_SIZE, window[0]), (META_WINDOW_OVERLAP, window[1])):
        entry = model.metadata_props.add()  # pyright: ignore[reportAttributeAccessIssue]
        entry.key, entry.value = key, str(value)
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
    values = "\n".join(
        f"| {name} | {value:.4f} |"
        for name, value in metrics["metrics"].items()
        if isinstance(value, float)
    )
    lengths = "\n".join(
        f"| {b['min_chars']}–{b['max_chars']} | {b['n']} | {b['fpr']:.4f} | {b['max']:.4f} |"
        for b in metrics["job_ad_fpr_by_length"]
    )
    window = metrics["window"]
    counts = metrics["metrics"]
    return f"""# Classifieur d'injection de prompt — {metrics["version"]}

Modèle maison de l'assistant « Interroge mon CV » : TF-IDF sur n-grammes de caractères (2 à 5)
et de mots (1 à 2), régression logistique pondérée, exporté en ONNX (aucun pickle).

- sha256 du modèle : `{metrics["model_sha256"]}`
- empreinte des données d'entraînement : `{metrics["dataset_fingerprint"]}`
- découpage servi : fenêtres de {window["size"]} caractères, chevauchement {window["overlap"]}, \
score = maximum sur les fenêtres (paramètres enregistrés dans les métadonnées ONNX)
- porte d'évaluation : **{"réussie" if metrics["passed"] else "échouée"}**

## Porte d'évaluation

| Contrôle | Valeur | Limite | Résultat |
|---|---|---|---|
{checks}

## Métriques (inférence servie : fenêtres et maximum)

| Métrique | Valeur |
|---|---|
{values}

Annonces légitimes d'évaluation, par longueur :

| Caractères | n | FPR | Score max |
|---|---|---|---|
{lengths}

## Données

{sources}
- `handwritten` — questions de recruteurs et attaques écrites à la main (FR/EN), dans le dépôt.
- `job_ads_train` — annonces synthétiques (FR/EN, 12 secteurs, jusqu'à ~9 000 caractères) \
générées par `python -m ml.job_ads`, légitimes ou avec une seule phrase d'injection. \
L'entraînement porte sur leurs fenêtres, étiquetées 1 si elles contiennent toute l'injection, \
0 si elles n'en contiennent rien.
- `job_ads_eval` — annonces synthétiques d'évaluation uniquement ({counts["n_job_ads_legit"]} \
légitimes, {counts["n_job_ads_injected"]} injectées), écrites avec des phrases jamais employées à \
l'entraînement.
- Ensemble adverse (`ml/data/adversarial.jsonl`) : évaluation uniquement, jamais vu à \
l'entraînement.
- Jeu du domaine (`ml/data/recruiter_eval.jsonl`) : 50 questions de recruteurs légitimes \
(tutoiement, vouvoiement, 3ᵉ personne, FR/EN), évaluation uniquement.
- Garde anti-fuite : aucun fichier du dépôt n'est quasi-doublon (Jaccard de mots ≥ 0,5) d'un jeu \
d'évaluation ; {counts["n_train_removed_near_duplicates"]} ligne(s) des sources publiques \
d'entraînement retirée(s) pour cette raison.

## Limites connues

- Détecteur lexical : une attaque reformulée sans vocabulaire d'injection peut passer ; le garde-fou
  de sortie reste la seconde ligne de défense.
- Seuil de décision 0,5, identique à `injection_threshold` dans `settings.yaml`.
- Une injection de plus de {window["overlap"]} caractères coupée à une frontière de fenêtre n'est \
vue qu'en partie.
- Les annonces d'évaluation sont synthétiques (même générateur que l'entraînement, phrases \
disjointes) ; les annonces réelles des évaluations de nuit restent le contrôle externe.
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


def load_repository_datasets() -> tuple[Datasets, list[Source]]:
    sources = load_sources()
    ds = build_datasets(
        sources,
        CACHE_DIR,
        HANDWRITTEN_PATH,
        ADVERSARIAL_PATH,
        RECRUITER_EVAL_PATH,
        job_ads_train=JOB_ADS_TRAIN_PATH,
        job_ads_eval=JOB_ADS_EVAL_PATH,
    )
    return ds, sources


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Entraîne et évalue le classifieur d'injection.")
    parser.add_argument("--version", required=True, help="ex. v1.0.0")
    parser.add_argument("--out", type=Path, default=Path("dist"))
    args = parser.parse_args(argv)
    if not VERSION_PATTERN.match(args.version):
        parser.error("la version doit ressembler à v1.2.3")

    ds, sources = load_repository_datasets()
    report = run_training(ds, args.version, args.out, load_gates(), sources)
    for check in report.checks:
        status = "OK" if check.passed else "KO"
        print(f"{status}  {check.name} = {check.value:.4f} (limite {check.limit})")
    for text in report.adversarial_failures:
        print(f"KO  adverse : {text}")
    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
