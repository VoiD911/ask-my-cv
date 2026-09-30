"""Dérive du classifieur d'injection : PSI des scores de production contre la référence du modèle.

python -m ml.drift --reference metrics.json --days 7 [--threshold 0.5] [--model-version V]
    [--log-group aws/spans] [--region ca-central-1]

Lit les scores `xops.score` des spans `injection` (hors trafic d'évaluation `xops.eval`) dans
CloudWatch Logs Insights sur `--days` jours, **pour la seule version promue** : la requête filtre
`xops.model_version` (par défaut `onnx-<version>` du `metrics.json`). Sans ce filtre, les jours
qui suivent une promotion mélangeaient les scores de l'ancien modèle à la référence du nouveau
(PSI 2,92 au lendemain de la promotion de v1.4.0, issue #124).

Deux populations, séparées par `xops.chars` (longueur de l'entrée, jamais le texte) :
- `questions` : moins de AD_MIN_CHARS caractères, contre `domain_question_score_histogram` ;
- `annonces` : AD_MIN_CHARS caractères ou plus (le seuil du second avis Bedrock Guardrails),
  contre `job_ad_score_histogram`.
Une référence sans ces histogrammes (modèle antérieur à v1.4.0) retombe sur une seule population,
contre `domain_score_histogram`. Les spans antérieurs à `xops.chars` n'entrent dans aucune
population séparée ; ils sont comptés dans le message.

Les scores ≥ `--threshold` (le seuil d'injection servi, `injection_threshold`) sont exclus des
deux côtés : ce sont des entrées bloquées, et une vague d'attaques ne doit pas passer pour une
dérive. Les compartiments de référence au-dessus du seuil sont donc ignorés.

Sous MIN_SAMPLES scores (après exclusion) dans une population, sa dérive n'est pas calculée :
« données insuffisantes », code 0, et une note dans le résumé du job GitHub
(`GITHUB_STEP_SUMMARY`). Le job échoue si le PSI d'une population atteint PSI_FAIL_THRESHOLD.

Une référence sans aucun histogramme (modèle antérieur à v1.2.0) produit un avertissement et un
code de sortie 0 : la dérive n'est pas calculable.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

MIN_SAMPLES = 30
PSI_FAIL_THRESHOLD = 0.2
PSI_WARN_THRESHOLD = 0.1
EPSILON = 1e-4
AD_MIN_CHARS = 400  # même seuil que le second avis (`guardrail_min_chars`)

POLL_INTERVAL_S = 2.0
MAX_POLLS = 30

MODEL_VERSION_PATTERN = re.compile(r"^onnx-v\d+\.\d+\.\d+$")


def logs_insights_query(model_version: str) -> str:
    """Requête Logs Insights des scores d'une version du modèle.

    Le span `injection` porte `attributes.xops.score`. Logs Insights aplatit le JSON en
    `attributes.xops.score` : le nom complet, points compris, se met entre backticks (vérifié
    sur `aws/spans` le 2026-09-26 ; la forme attributes.`xops.score` renvoie un champ vide).
    Les spans sans score (étape en erreur avant la mesure) sont écartés par `isPresent`. La
    version est validée avant d'entrer dans la requête.
    """
    if not MODEL_VERSION_PATTERN.match(model_version):
        raise ValueError(f"version de modèle invalide : {model_version!r}")
    return (
        'filter name = "injection" and not isPresent(`attributes.xops.eval`)'
        " and isPresent(`attributes.xops.score`)"
        f' and `attributes.xops.model_version` = "{model_version}"\n'
        "| fields `attributes.xops.score` as score, `attributes.xops.chars` as chars\n"
        "| limit 10000"
    )


@dataclass(frozen=True)
class Sample:
    score: float
    chars: int | None  # None : span antérieur à `xops.chars`


class DriftError(RuntimeError):
    """La requête Logs Insights a échoué ou n'a pas abouti à temps."""


def psi(reference_counts: Sequence[int], production_counts: Sequence[int]) -> float:
    """Population Stability Index entre deux histogrammes de comptages (mêmes compartiments)."""
    if len(reference_counts) != len(production_counts):
        raise ValueError("les histogrammes doivent avoir la même longueur")
    reference_total = sum(reference_counts)
    production_total = sum(production_counts)
    total = 0.0
    for ref_count, prod_count in zip(reference_counts, production_counts, strict=True):
        ref_share = (ref_count / reference_total if reference_total else 0.0) + EPSILON
        prod_share = (prod_count / production_total if production_total else 0.0) + EPSILON
        total += (prod_share - ref_share) * math.log(prod_share / ref_share)
    return total


def histogram(scores: Sequence[float]) -> list[int]:
    """10 compartiments sur [0, 1] ; un score de 1.0 tombe dans le dernier."""
    counts, _ = np.histogram(np.asarray(scores, dtype=float), bins=10, range=(0.0, 1.0))
    return [int(c) for c in counts]


def _row_value(row: list[dict[str, str]], field: str) -> str | None:
    for entry in row:
        if entry.get("field") == field:
            return entry["value"]
    return None


def _sample(row: list[dict[str, str]]) -> Sample:
    score = _row_value(row, "score")
    if score is None:
        raise DriftError(f"champ « score » absent de la ligne de résultat : {row}")
    chars = _row_value(row, "chars")
    return Sample(float(score), int(float(chars)) if chars not in (None, "") else None)


def fetch_scores(
    client: Any,
    log_group: str,
    start: int,
    end: int,
    model_version: str,
    *,
    poll_interval: float = POLL_INTERVAL_S,
    max_polls: int = MAX_POLLS,
    sleep: Callable[[float], None] = time.sleep,
) -> list[Sample]:
    """Lance la requête Logs Insights et attend les résultats (borné dans le temps)."""
    started = client.start_query(
        logGroupName=log_group,
        startTime=start,
        endTime=end,
        queryString=logs_insights_query(model_version),
    )
    query_id = started["queryId"]
    for _ in range(max_polls):
        result = client.get_query_results(queryId=query_id)
        status = result["status"]
        if status == "Complete":
            return [_sample(row) for row in result["results"]]
        if status == "Failed":
            raise DriftError(f"requête Logs Insights échouée pour {log_group} (queryId={query_id})")
        sleep(poll_interval)
    raise DriftError(f"délai dépassé en attendant les résultats Logs Insights (queryId={query_id})")


def _default_client_factory(region: str) -> Any:
    import boto3

    return boto3.client("logs", region_name=region)


def below_threshold(counts: Sequence[int], threshold: float) -> list[int]:
    """Compartiments de référence au-dessus du seuil mis à zéro (entrées bloquées exclues)."""
    return [c if i / len(counts) < threshold else 0 for i, c in enumerate(counts)]


@dataclass(frozen=True)
class Population:
    name: str
    reference: list[int]
    scores: list[float]
    excluded: int


def populations(reference: dict, samples: list[Sample], threshold: float) -> list[Population]:
    """Populations à comparer, selon les histogrammes disponibles dans la référence."""

    def build(name: str, key: str, kept: list[Sample]) -> Population:
        scores = [s.score for s in kept if s.score < threshold]
        counts = below_threshold(reference[key]["counts"], threshold)
        return Population(name, counts, scores, len(kept) - len(scores))

    split = "domain_question_score_histogram" in reference and "job_ad_score_histogram" in reference
    if not split:
        return [build("domaine", "domain_score_histogram", samples)]
    known = [s for s in samples if s.chars is not None]
    return [
        build(
            "questions",
            "domain_question_score_histogram",
            [s for s in known if s.chars is not None and s.chars < AD_MIN_CHARS],
        ),
        build(
            "annonces",
            "job_ad_score_histogram",
            [s for s in known if s.chars is not None and s.chars >= AD_MIN_CHARS],
        ),
    ]


def _summary(line: str) -> None:
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if path:
        with open(path, "a", encoding="utf-8") as f:
            f.write(line + "\n")


def main(
    argv: Sequence[str] | None = None,
    *,
    client_factory: Callable[[str], Any] = _default_client_factory,
    fetch_scores: Callable[..., list[Sample]] = fetch_scores,
) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference", required=True, help="metrics.json de la release promue")
    parser.add_argument("--days", type=int, default=7, help="fenêtre glissante en jours")
    parser.add_argument(
        "--threshold",
        type=float,
        default=0.5,
        help="seuil d'injection servi : les scores au-dessus (attaques bloquées) sont exclus",
    )
    parser.add_argument(
        "--model-version",
        help="valeur de xops.model_version à retenir (défaut : onnx-<version du metrics.json>)",
    )
    parser.add_argument("--log-group", default="aws/spans")
    parser.add_argument("--region", default="ca-central-1")
    args = parser.parse_args(argv)

    reference = json.loads(Path(args.reference).read_text(encoding="utf-8"))
    if "domain_score_histogram" not in reference:
        print(
            "::warning::référence sans domain_score_histogram (modèle antérieur à v1.2.0) : "
            "dérive non calculée"
        )
        return 0
    model_version = args.model_version or f"onnx-{reference.get('version', '')}"
    logs_insights_query(model_version)  # refuse une version mal formée avant tout appel AWS

    end = int(time.time())
    start = end - args.days * 86400
    client = client_factory(args.region)
    samples = fetch_scores(client, args.log_group, start, end, model_version)
    unknown = sum(s.chars is None for s in samples)
    print(
        f"{len(samples)} score(s) de {model_version} sur {args.days} jours"
        + (f" dont {unknown} sans longueur (spans antérieurs à xops.chars)." if unknown else ".")
    )

    failed = False
    for pop in populations(reference, samples, args.threshold):
        n = len(pop.scores)
        if n < MIN_SAMPLES:
            message = (
                f"{pop.name} : données insuffisantes, {n} score(s) sous le seuil {args.threshold} "
                f"({pop.excluded} exclu(s), minimum {MIN_SAMPLES}) ; dérive non calculée."
            )
            print(message)
            _summary(f"- Dérive {model_version}, {message}")
            continue
        value = psi(pop.reference, histogram(pop.scores))
        detail = f"PSI={value:.4f} ({n} scores, {pop.excluded} bloqué(s) exclu(s))"
        if value >= PSI_FAIL_THRESHOLD:
            print(f"{pop.name} : dérive du classifieur détectée : {detail} ≥ {PSI_FAIL_THRESHOLD}.")
            failed = True
        elif value >= PSI_WARN_THRESHOLD:
            print(f"::warning::{pop.name} : dérive du classifieur en observation : {detail}.")
        else:
            print(f"{pop.name} : pas de dérive significative : {detail}.")
        _summary(f"- Dérive {model_version}, {pop.name} : {detail}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
