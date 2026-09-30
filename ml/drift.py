"""Dérive du classifieur d'injection : scores de production de la version promue.

python -m ml.drift --reference metrics.json [--days 7] [--baseline-days 28] [--threshold 0.5]
    [--model-version V] [--settings settings.aws.yaml] [--log-group aws/spans]
    [--region ca-central-1]

Une seule requête Logs Insights lit les spans `injection` (hors trafic d'évaluation `xops.eval`)
des `days + baseline-days` derniers jours : score (`xops.score`), longueur de l'entrée
(`xops.chars`, jamais le texte), version du modèle (`xops.model_version`) et horodatage. Seule
la version promue est comparée (par défaut `onnx-<version>` du `metrics.json`).

Populations, séparées par la longueur, au seuil du second avis Bedrock Guardrails
(`guardrail_min_chars` des réglages de production, 400) appliqué au même texte replié :
`questions` (plus courtes) et `annonces` (au moins ce seuil).

Référence. Les histogrammes du `metrics.json` viennent du jeu d'évaluation (en partie
synthétique) : les vraies questions n'ont aucune raison de suivre cette distribution. Tant
qu'aucune référence de production n'existe, chaque population est comparée **à elle-même dans
le temps** : les `days` derniers jours contre les `baseline-days` jours précédents, même version.
La comparaison à la référence d'évaluation n'est qu'un avertissement, jamais un échec.

Statistique. Scores ≥ seuil servi exclus des deux côtés (entrées bloquées) ; le seuil doit
tomber sur un bord de compartiment (0,1). Compartiments de 0,1 sous le seuil, fusionnés deux à
deux sous LARGE_SAMPLE scores. Lissage de Laplace (+0,5 par compartiment, des deux côtés). Le PSI
observé est comparé à sa distribution sous l'hypothèse nulle : BOOTSTRAP_DRAWS tirages de n
scores dans l'histogramme de base (graine fixe). Échec au-delà du 99e centile, avertissement au-
delà du 95e. Un seuil fixe (0,2) ne vaut que pour de grands échantillons : à n = 30 et dix
compartiments, le bruit seul le dépasse.

Échecs explicites (le job `report` ouvre alors une issue) :
- aucune donnée exploitable pour la version promue alors que d'autres versions ont des spans
  sur la période récente (version mal alignée) ;
- résultat tronqué (autant de lignes que la limite de la requête) ;
- aucun span sur toute la période ;
- population sous MIN_SAMPLES scores sur les STALE_DAYS derniers jours alors que la version
  (et `xops.chars`) est en service depuis au moins STALE_DAYS jours : la dérive n'aurait pas été
  évaluée depuis deux semaines. Sinon, sous MIN_SAMPLES sur `days` : « données insuffisantes »,
  succès et note dans le résumé du job. Aucun état n'est stocké : tout se lit dans la requête.

Une référence sans `domain_score_histogram` (modèle antérieur à v1.2.0) produit un
avertissement et un code de sortie 0 : la dérive n'est pas calculable.
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
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import yaml

from ask_my_cv.settings import Settings

MIN_SAMPLES = 30
LARGE_SAMPLE = 100
STALE_DAYS = 14
BOOTSTRAP_DRAWS = 5000
FAIL_QUANTILE = 0.99
WARN_QUANTILE = 0.95
SMOOTHING = 0.5
BIN_WIDTH = 0.1
QUERY_LIMIT = 10000

POLL_INTERVAL_S = 2.0
MAX_POLLS = 30

MODEL_VERSION_PATTERN = re.compile(r"^onnx-v\d+\.\d+\.\d+$")

# Le span `injection` porte `attributes.xops.*`. Logs Insights aplatit le JSON : le nom complet,
# points compris, se met entre backticks (vérifié sur `aws/spans` le 2026-09-26 pour
# `xops.score` ; `xops.chars` suit le même chemin, à confirmer sur un span réel). Les spans sans
# score (étape en erreur avant la mesure) sont écartés par `isPresent`.
LOGS_INSIGHTS_QUERY = (
    'filter name = "injection" and not isPresent(`attributes.xops.eval`)'
    " and isPresent(`attributes.xops.score`)\n"
    "| fields `attributes.xops.score` as score, `attributes.xops.chars` as chars,"
    " `attributes.xops.model_version` as model_version, @timestamp as ts\n"
    f"| limit {QUERY_LIMIT}"
)


@dataclass(frozen=True)
class Sample:
    score: float
    chars: int | None  # None : span antérieur à `xops.chars`
    version: str = ""
    ts: float = 0.0  # secondes depuis l'époque


class DriftError(RuntimeError):
    """Requête Logs Insights en échec, résultat inexploitable ou configuration incohérente."""


def validate_version(model_version: str) -> str:
    if not MODEL_VERSION_PATTERN.match(model_version):
        raise ValueError(f"version de modèle invalide : {model_version!r}")
    return model_version


def parse_chars(value: object) -> int | None:
    """`xops.chars` arrive en nombre ou en chaîne selon l'export ; vide ou absent : None."""
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        raise DriftError(f"longueur invalide : {value!r}")
    try:
        number = float(value)  # pyright: ignore[reportArgumentType]
    except (TypeError, ValueError) as exc:
        raise DriftError(f"longueur invalide : {value!r}") from exc
    if not number.is_integer() or number < 0:
        raise DriftError(f"longueur invalide : {value!r}")
    return int(number)


def parse_timestamp(value: str | None) -> float:
    """@timestamp de Logs Insights (« 2026-09-30 01:02:03.456 », UTC) ou millisecondes."""
    if not value:
        raise DriftError("horodatage absent")
    if value.isdigit():
        return int(value) / 1000
    return datetime.strptime(value, "%Y-%m-%d %H:%M:%S.%f").replace(tzinfo=UTC).timestamp()


def ad_min_chars(settings_path: Path) -> int:
    """Seuil « annonce » des réglages servis (`guardrail_min_chars`), défaut du modèle sinon."""
    default = Settings.model_fields["guardrail_min_chars"].default
    if not settings_path.exists():
        return int(default)
    data = yaml.safe_load(settings_path.read_text(encoding="utf-8")) or {}
    return int(data.get("guardrail_min_chars", default))


def _row_value(row: list[dict[str, str]], field: str) -> str | None:
    for entry in row:
        if entry.get("field") == field:
            return entry["value"]
    return None


def _sample(row: list[dict[str, str]]) -> Sample:
    score = _row_value(row, "score")
    if score is None:
        raise DriftError(f"champ « score » absent de la ligne de résultat : {row}")
    return Sample(
        float(score),
        parse_chars(_row_value(row, "chars")),
        _row_value(row, "model_version") or "",
        parse_timestamp(_row_value(row, "ts")),
    )


def fetch_scores(
    client: Any,
    log_group: str,
    start: int,
    end: int,
    *,
    poll_interval: float = POLL_INTERVAL_S,
    max_polls: int = MAX_POLLS,
    sleep: Callable[[float], None] = time.sleep,
) -> list[Sample]:
    """Lance la requête Logs Insights et attend les résultats (borné dans le temps)."""
    started = client.start_query(
        logGroupName=log_group, startTime=start, endTime=end, queryString=LOGS_INSIGHTS_QUERY
    )
    query_id = started["queryId"]
    for _ in range(max_polls):
        result = client.get_query_results(queryId=query_id)
        status = result["status"]
        if status == "Complete":
            rows = result["results"]
            if len(rows) >= QUERY_LIMIT:
                raise DriftError(
                    f"résultat tronqué : {len(rows)} lignes, limite {QUERY_LIMIT} atteinte"
                )
            return [_sample(row) for row in rows]
        if status == "Failed":
            raise DriftError(f"requête Logs Insights échouée pour {log_group} (queryId={query_id})")
        sleep(poll_interval)
    raise DriftError(f"délai dépassé en attendant les résultats Logs Insights (queryId={query_id})")


def _default_client_factory(region: str) -> Any:
    import boto3

    return boto3.client("logs", region_name=region)


# --- Statistique ------------------------------------------------------------------------------


def kept_bins(threshold: float) -> int:
    """Nombre de compartiments de 0,1 sous le seuil ; le seuil doit tomber sur un bord."""
    k = round(threshold / BIN_WIDTH)
    if k < 1 or not math.isclose(k * BIN_WIDTH, threshold, abs_tol=1e-9):
        raise ValueError(f"le seuil {threshold} doit être un multiple de {BIN_WIDTH}")
    return k


def counts_below(scores: Sequence[float], threshold: float) -> np.ndarray:
    k = kept_bins(threshold)
    values = np.asarray([s for s in scores if s < threshold], dtype=float)
    counts, _ = np.histogram(values, bins=k, range=(0.0, k * BIN_WIDTH))
    return counts


def coarsen(counts: np.ndarray, n: int) -> np.ndarray:
    """Sous LARGE_SAMPLE scores, fusion des compartiments deux à deux (moins de bruit)."""
    if n >= LARGE_SAMPLE or len(counts) <= 2:
        return np.asarray(counts, dtype=float)
    padded = np.append(counts, 0) if len(counts) % 2 else counts
    return np.asarray(padded, dtype=float).reshape(-1, 2).sum(axis=1)


def psi(reference: Sequence[float] | np.ndarray, production: Sequence[float] | np.ndarray) -> float:
    """PSI entre deux histogrammes de comptages, lissage de Laplace (+0,5) des deux côtés."""
    if len(reference) != len(production):
        raise ValueError("les histogrammes doivent avoir la même longueur")
    ref = np.asarray(reference, dtype=float) + SMOOTHING
    prod = np.asarray(production, dtype=float) + SMOOTHING
    ref, prod = ref / ref.sum(), prod / prod.sum()
    return float(np.sum((prod - ref) * np.log(prod / ref)))


def null_quantiles(
    reference: Sequence[float] | np.ndarray, n: int, seed: int = 0
) -> tuple[float, float]:
    """95e et 99e centiles du PSI de n scores tirés dans la référence elle-même."""
    probs = np.asarray(reference, dtype=float)
    probs = probs / probs.sum()
    rng = np.random.default_rng(seed)
    draws = rng.multinomial(n, probs, size=BOOTSTRAP_DRAWS) + SMOOTHING
    ref = np.asarray(reference, dtype=float) + SMOOTHING
    ref = ref / ref.sum()
    prod = draws / draws.sum(axis=1, keepdims=True)
    values = np.sum((prod - ref) * np.log(prod / ref), axis=1)  # même formule que `psi`
    # "higher" : centile pris sur une valeur tirée, jamais interpolé vers le bas (PSI discret)
    warn, fail = (
        float(np.quantile(values, q, method="higher")) for q in (WARN_QUANTILE, FAIL_QUANTILE)
    )
    return warn, fail


@dataclass(frozen=True)
class Verdict:
    level: str  # "ok", "warning", "fail"
    value: float
    warn_at: float
    fail_at: float
    bins: int


def compare(reference_counts: np.ndarray, production_counts: np.ndarray) -> Verdict:
    """PSI observé contre la distribution nulle du PSI, à la même taille d'échantillon."""
    n = int(production_counts.sum())
    reference = coarsen(reference_counts, n)
    production = coarsen(production_counts, n)
    value = psi(reference, production)
    warn_at, fail_at = null_quantiles(reference, n)
    level = "fail" if value > fail_at else "warning" if value > warn_at else "ok"
    return Verdict(level, value, warn_at, fail_at, len(reference))


# --- Orchestration ----------------------------------------------------------------------------


def _summary(line: str) -> None:
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if path:
        with open(path, "a", encoding="utf-8") as f:
            f.write(line + "\n")


def _say(line: str) -> None:
    print(line)
    _summary(f"- {line.removeprefix('::warning::').removeprefix('::error::')}")


def main(
    argv: Sequence[str] | None = None,
    *,
    client_factory: Callable[[str], Any] = _default_client_factory,
    fetch_scores: Callable[..., list[Sample]] = fetch_scores,
    now: Callable[[], float] = time.time,
) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference", required=True, help="metrics.json de la release promue")
    parser.add_argument("--days", type=int, default=7, help="période récente, en jours")
    parser.add_argument("--baseline-days", type=int, default=28, help="période de base")
    parser.add_argument("--threshold", type=float, default=0.5, help="seuil d'injection servi")
    parser.add_argument("--model-version", help="xops.model_version (défaut : onnx-<version>)")
    parser.add_argument("--settings", type=Path, default=Path("settings.aws.yaml"))
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
    try:
        version = validate_version(args.model_version or f"onnx-{reference.get('version', '')}")
        kept_bins(args.threshold)
    except ValueError as exc:
        print(f"::error::{exc}")
        return 1
    min_chars = ad_min_chars(args.settings)

    end = int(now())
    recent_start = end - args.days * 86400
    stale_start = end - max(STALE_DAYS, args.days) * 86400
    start = end - (args.days + args.baseline_days) * 86400
    try:
        samples = fetch_scores(client_factory(args.region), args.log_group, start, end)
    except DriftError as exc:
        print(f"::error::{exc}")
        return 1

    if not samples:
        _say(
            f"::error::aucun span `injection` sur {args.days + args.baseline_days} jours : "
            "export des traces ou requête à vérifier."
        )
        return 1
    recent_all = [s for s in samples if s.ts >= recent_start]
    mine = [s for s in samples if s.version == version]
    if recent_all and not [s for s in recent_all if s.version == version]:
        others = sorted({s.version for s in recent_all})
        _say(
            f"::error::aucun span de {version} sur {args.days} jours alors que d'autres versions "
            f"en ont ({', '.join(others)}) : version promue mal alignée avec la production."
        )
        return 1
    unknown = sum(s.chars is None for s in mine)
    print(
        f"{len(mine)} score(s) de {version} sur {args.days + args.baseline_days} jours"
        + (f", dont {unknown} sans longueur (spans antérieurs à xops.chars)." if unknown else ".")
    )

    # Règle des deux semaines sans état : la dérive n'a pas pu être évaluée depuis STALE_DAYS si
    # la version (et `xops.chars`) est en service depuis au moins autant et que la fenêtre de
    # STALE_DAYS jours reste sous MIN_SAMPLES. Avant, simple « données insuffisantes ».
    with_chars = [s.ts for s in mine if s.chars is not None]
    oldest = min(with_chars) if with_chars else min((s.ts for s in mine), default=None)
    in_service = oldest is not None and oldest <= stale_start
    split = {"questions": "domain_question_score_histogram", "annonces": "job_ad_score_histogram"}
    failed = False
    for name, key in split.items():
        pop = [
            s
            for s in mine
            if s.chars is not None and (s.chars >= min_chars) == (name == "annonces")
        ]
        recent = [s.score for s in pop if s.ts >= recent_start]
        baseline = [s.score for s in pop if s.ts < recent_start]
        stale = [s.score for s in pop if s.ts >= stale_start and s.score < args.threshold]
        recent_counts = counts_below(recent, args.threshold)
        n = int(recent_counts.sum())
        if n < MIN_SAMPLES:
            if in_service and len(stale) < MIN_SAMPLES:
                _say(
                    f"::error::{name} : {len(stale)} score(s) exploitable(s) sur {STALE_DAYS} "
                    f"jours (minimum {MIN_SAMPLES}) : dérive non évaluée depuis deux semaines."
                )
                failed = True
            else:
                _say(
                    f"{name} : données insuffisantes, {n} score(s) sur {args.days} jours "
                    f"(minimum {MIN_SAMPLES}) ; dérive non calculée."
                )
            continue
        base_counts = counts_below(baseline, args.threshold)
        if base_counts.sum() >= MIN_SAMPLES:
            v = compare(base_counts, recent_counts)
            detail = (
                f"{name} ({args.days} j contre {args.baseline_days} j précédents) : "
                f"PSI={v.value:.4f}, n={n}, {v.bins} compartiments, "
                f"alerte > {v.fail_at:.4f} (99e centile nul)"
            )
            if v.level == "fail":
                _say(f"::error::dérive détectée, {detail}.")
                failed = True
            elif v.level == "warning":
                _say(f"::warning::dérive en observation, {detail}.")
            else:
                _say(f"pas de dérive significative, {detail}.")
        else:
            _say(
                f"{name} : période de base trop courte ({int(base_counts.sum())} scores), "
                "comparaison à la référence d'évaluation seulement."
            )
        if key in reference:
            synthetic = np.asarray(reference[key]["counts"][: kept_bins(args.threshold)])
            if synthetic.sum() > 0:
                v = compare(synthetic, recent_counts)
                if v.level != "ok":
                    # jeu d'évaluation (synthétique) : information, jamais un échec
                    _say(
                        f"::warning::{name} : écart à la référence d'évaluation, "
                        f"PSI={v.value:.4f} (alerte nulle > {v.fail_at:.4f}) ; informatif."
                    )
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
