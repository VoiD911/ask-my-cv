"""Dérive du classifieur d'injection : PSI des scores de production contre le domaine.

python -m ml.drift --reference metrics.json --days 7 [--log-group aws/spans] [--region ca-central-1]

Lit les scores `xops.score` des spans `injection` (hors trafic d'évaluation `xops.eval`) dans
CloudWatch Logs Insights sur `--days` jours, et calcule le PSI (Population Stability Index)
contre `domain_score_histogram` du `metrics.json` de la release promue.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

import numpy as np

MIN_SAMPLES = 50
PSI_FAIL_THRESHOLD = 0.2
PSI_WARN_THRESHOLD = 0.1
EPSILON = 1e-4

POLL_INTERVAL_S = 2.0
MAX_POLLS = 30

# Le span `injection` porte `attributes.xops.score`. Logs Insights aplatit le JSON en
# `attributes.xops.score` : le nom complet, points compris, se met entre backticks (vérifié sur
# `aws/spans` le 2026-09-26 ; la forme attributes.`xops.score` renvoie un champ vide).
LOGS_INSIGHTS_QUERY = (
    'filter name = "injection" and not isPresent(`attributes.xops.eval`)\n'
    "| fields `attributes.xops.score` as score\n"
    "| limit 10000"
)


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


def _row_value(row: list[dict[str, str]], field: str) -> str:
    for entry in row:
        if entry.get("field") == field:
            return entry["value"]
    raise DriftError(f"champ « {field} » absent de la ligne de résultat : {row}")


def fetch_scores(
    client: Any,
    log_group: str,
    start: int,
    end: int,
    *,
    poll_interval: float = POLL_INTERVAL_S,
    max_polls: int = MAX_POLLS,
    sleep: Callable[[float], None] = time.sleep,
) -> list[float]:
    """Lance la requête Logs Insights et attend les résultats (borné dans le temps)."""
    started = client.start_query(
        logGroupName=log_group,
        startTime=start,
        endTime=end,
        queryString=LOGS_INSIGHTS_QUERY,
    )
    query_id = started["queryId"]
    for _ in range(max_polls):
        result = client.get_query_results(queryId=query_id)
        status = result["status"]
        if status == "Complete":
            return [float(_row_value(row, "score")) for row in result["results"]]
        if status == "Failed":
            raise DriftError(f"requête Logs Insights échouée pour {log_group} (queryId={query_id})")
        sleep(poll_interval)
    raise DriftError(f"délai dépassé en attendant les résultats Logs Insights (queryId={query_id})")


def _default_client_factory(region: str) -> Any:
    import boto3

    return boto3.client("logs", region_name=region)


def main(
    argv: Sequence[str] | None = None,
    *,
    client_factory: Callable[[str], Any] = _default_client_factory,
    fetch_scores: Callable[..., list[float]] = fetch_scores,
) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference", required=True, help="metrics.json de la release promue")
    parser.add_argument("--days", type=int, default=7, help="fenêtre glissante en jours")
    parser.add_argument("--log-group", default="aws/spans")
    parser.add_argument("--region", default="ca-central-1")
    args = parser.parse_args(argv)

    reference = json.loads(Path(args.reference).read_text(encoding="utf-8"))
    reference_counts = reference["domain_score_histogram"]["counts"]

    end = int(time.time())
    start = end - args.days * 86400

    client = client_factory(args.region)
    scores = fetch_scores(client, args.log_group, start, end)

    if len(scores) < MIN_SAMPLES:
        print(
            f"données insuffisantes : {len(scores)} score(s) sur les {args.days} derniers "
            f"jours (minimum {MIN_SAMPLES})."
        )
        return 0

    production_counts = histogram(scores)
    value = psi(reference_counts, production_counts)

    if value >= PSI_FAIL_THRESHOLD:
        print(
            f"dérive du classifieur détectée : PSI={value:.4f} ≥ {PSI_FAIL_THRESHOLD} "
            f"({len(scores)} scores sur {args.days} jours)."
        )
        return 1
    if value >= PSI_WARN_THRESHOLD:
        print(
            f"::warning::dérive du classifieur en observation : PSI={value:.4f} "
            f"(seuil d'échec {PSI_FAIL_THRESHOLD}, {len(scores)} scores sur {args.days} jours)."
        )
        return 0
    print(f"pas de dérive significative : PSI={value:.4f} ({len(scores)} scores).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
