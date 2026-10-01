"""Résumé hebdomadaire de l'usage réel de la démo (#143), envoyé au sujet SNS des alertes.

python infra/scripts/weekly_summary.py [--dry-run] [--region ca-central-1]
    [--log-group aws/spans] [--topic-name ask-my-cv-alerts] [--now <horodatage UNIX>]

Lit les spans racine `ask` du trafic public (`xops.traffic = public`, #143) dans CloudWatch
Logs Insights, pour la dernière semaine ISO complète (lundi 00:00 UTC au lundi suivant) et la
précédente, puis publie un court courriel en français : visiteurs, requêtes, questions et
annonces, attaques bloquées, refus, réponses retirées, coût, langue principale. Jamais le
texte d'une question : les spans n'en contiennent pas.

`--dry-run` affiche le message au lieu de le publier (aucun appel SNS). Lancé chaque lundi par
.github/workflows/weekly.yml avec le rôle OIDC de nuit (Logs Insights en lecture, sns:Publish
sur ce seul sujet).
"""

from __future__ import annotations

import argparse
import sys
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

POLL_INTERVAL_S = 2.0
MAX_POLLS = 60
WEEK_S = 7 * 86400

# Trafic public uniquement : évaluations, tests de fumée et propriétaire sont `internal`.
PUBLIC = 'filter name = "ask" and `attributes.xops.traffic` = "public"\n'

QUERIES: dict[str, str] = {
    "totals": PUBLIC
    + "| fields `attributes.xops.kind` as kind, `attributes.xops.result` as result,"
    " `attributes.xops.refusal` as refused, `attributes.xops.withdrawn` as pulled,"
    " `attributes.xops.cost_usd` as usd\n"
    '| stats count(*) as requests, sum(kind = "question") as questions,'
    ' sum(kind = "ad") as ads, sum(result = "injection_detected") as attacks,'
    " sum(refused) as refusals, sum(pulled) as withdrawn, sum(usd) as spent",
    # deux agrégations : décompte exact (count_distinct est approximatif dans Logs Insights)
    "visitors": PUBLIC + "| stats count(*) as n by `attributes.xops.visitor` as visitor\n"
    "| stats count(*) as visitors",
    "languages": PUBLIC + "| filter isPresent(`attributes.xops.language`)\n"
    "| stats count(*) as n by `attributes.xops.language` as language\n"
    "| sort n desc",
    # coût de tout le trafic (évaluations comprises) : c'est lui qui consomme le plafond
    "all_cost": 'filter name = "ask"\n| stats sum(`attributes.xops.cost_usd`) as cost',
}

LANGUAGES = {"fr": "français", "en": "anglais"}


class SummaryError(RuntimeError):
    """Une requête Logs Insights a échoué ou n'a pas abouti à temps."""


@dataclass(frozen=True)
class Week:
    start: datetime
    end: datetime

    @property
    def label(self) -> str:
        last = self.end - timedelta(days=1)
        return f"du {self.start:%Y-%m-%d} au {last:%Y-%m-%d}"


@dataclass(frozen=True)
class Stats:
    visitors: int = 0
    requests: int = 0
    questions: int = 0
    ads: int = 0
    attacks: int = 0
    refusals: int = 0
    withdrawn: int = 0
    cost_usd: float = 0.0
    all_cost_usd: float = 0.0
    top_language: str | None = None
    top_language_share: float = 0.0


def last_full_weeks(now: float) -> tuple[Week, Week]:
    """Dernière semaine ISO complète (UTC) et la précédente."""
    today = datetime.fromtimestamp(now, UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    monday = today - timedelta(days=today.weekday())
    current = Week(monday - timedelta(days=7), monday)
    previous = Week(current.start - timedelta(days=7), current.start)
    return current, previous


Rows = list[dict[str, str]]


def run_query(
    client: Any,
    log_group: str,
    query: str,
    week: Week,
    *,
    poll_interval: float = POLL_INTERVAL_S,
    max_polls: int = MAX_POLLS,
    sleep: Callable[[float], None] = time.sleep,
    not_before: int = 0,
) -> Rows:
    """Lance une requête Logs Insights et attend ses résultats (borné dans le temps).

    `not_before` : début de la rétention du groupe ; Logs Insights refuse une plage qui la
    dépasse, et les spans plus anciens ont de toute façon expiré.
    """
    start = max(int(week.start.timestamp()), not_before)
    # endTime inclusif : on s'arrête juste avant le lundi suivant
    end = int(week.end.timestamp()) - 1
    if start >= end:
        return []
    started = client.start_query(
        logGroupName=log_group, startTime=start, endTime=end, queryString=query
    )
    query_id = started["queryId"]
    for _ in range(max_polls):
        result = client.get_query_results(queryId=query_id)
        status = result["status"]
        if status == "Complete":
            return [{f["field"]: f["value"] for f in row} for row in result["results"]]
        if status in {"Failed", "Cancelled", "Timeout"}:
            raise SummaryError(f"requête Logs Insights {status} (queryId={query_id})")
        sleep(poll_interval)
    raise SummaryError(f"délai dépassé en attendant Logs Insights (queryId={query_id})")


def _int(row: Mapping[str, str], key: str) -> int:
    value = row.get(key)
    return int(float(value)) if value not in (None, "") else 0


def _float(row: Mapping[str, str], key: str) -> float:
    value = row.get(key)
    return float(value) if value not in (None, "") else 0.0


def to_stats(results: Mapping[str, Rows]) -> Stats:
    """Résultats bruts des QUERIES (une liste de lignes par requête) vers des Stats."""
    totals = (results.get("totals") or [{}])[0]
    visitors = (results.get("visitors") or [{}])[0]
    all_cost = (results.get("all_cost") or [{}])[0]
    languages = [r for r in results.get("languages", []) if r.get("language")]
    counted = sum(_int(r, "n") for r in languages)
    top = max(languages, key=lambda r: _int(r, "n"), default=None)
    return Stats(
        visitors=_int(visitors, "visitors"),
        requests=_int(totals, "requests"),
        questions=_int(totals, "questions"),
        ads=_int(totals, "ads"),
        attacks=_int(totals, "attacks"),
        refusals=_int(totals, "refusals"),
        withdrawn=_int(totals, "withdrawn"),
        cost_usd=_float(totals, "spent"),
        all_cost_usd=_float(all_cost, "cost"),
        top_language=top["language"] if top else None,
        top_language_share=_int(top, "n") / counted if top and counted else 0.0,
    )


def fetch_stats(client: Any, log_group: str, week: Week, **kwargs: Any) -> Stats:
    return to_stats(
        {
            name: run_query(client, log_group, query, week, **kwargs)
            for name, query in QUERIES.items()
        }
    )


def _trend(current: float, previous: float) -> str:
    if previous == 0:
        return "nouveau" if current else "stable"
    change = (current - previous) / previous * 100
    return "stable" if abs(change) < 0.5 else f"{change:+.0f} %"


def _line(label: str, current: float, previous: float | None, shown: str = "") -> str:
    shown = shown or f"{current:g}"
    if previous is None:
        return f"- {label} : {shown} (semaine précédente : indisponible)"
    before = _usd(previous) if shown.endswith("USD") else f"{previous:g}"
    return f"- {label} : {shown} (semaine précédente : {before}, {_trend(current, previous)})"


def _usd(value: float) -> str:
    return f"{value:.2f} USD".replace(".", ",")


def format_summary(week: Week, current: Stats, previous: Stats | None) -> tuple[str, str]:
    """Objet (ASCII, exigé par SNS) et corps du courriel, en français.

    `previous` vaut None si la semaine précédente n'est pas lisible (avant la création du
    groupe de journaux ou hors rétention) : pas de comparaison."""

    def before(field: str) -> float | None:
        return None if previous is None else getattr(previous, field)

    subject = f"ask-my-cv : resume hebdomadaire ({week.start:%Y-%m-%d})"
    if current.top_language:
        name = LANGUAGES.get(current.top_language, current.top_language)
        language = f"{name} ({current.top_language_share:.0%})".replace("%", " %")
    else:
        language = "aucune donnée"
    lines = [
        f"Usage public de https://job.stevelang.net, semaine {week.label} (UTC).",
        "Trafic interne exclu (évaluations, tests de fumée, propriétaire).",
        "",
        _line("Visiteurs distincts", current.visitors, before("visitors")),
        _line("Requêtes", current.requests, before("requests")),
        _line("Questions", current.questions, before("questions")),
        _line("Annonces collées", current.ads, before("ads")),
        _line("Attaques bloquées", current.attacks, before("attacks")),
        _line("Refus (hors CV)", current.refusals, before("refusals")),
        _line("Réponses retirées par le garde de sortie", current.withdrawn, before("withdrawn")),
        _line(
            "Coût du trafic public",
            current.cost_usd,
            before("cost_usd"),
            shown=_usd(current.cost_usd),
        ),
        f"- Coût total mesuré, interne compris : {_usd(current.all_cost_usd)}",
        f"- Langue principale : {language}",
        "",
        "Aucun texte de question n'est conservé : ces chiffres viennent des attributs xops.*",
        "des spans (aws/spans). Détail : tableau de bord CloudWatch « ask-my-cv-usage ».",
    ]
    if current.requests == 0:
        lines.insert(3, "Aucune requête publique cette semaine.\n")
    return subject, "\n".join(lines) + "\n"


def _clients(region: str) -> tuple[Any, Any, Any]:
    import boto3

    return (
        boto3.client("logs", region_name=region),
        boto3.client("sns", region_name=region),
        boto3.client("sts", region_name=region),
    )


def main(
    argv: Sequence[str] | None = None,
    *,
    clients: Callable[[str], tuple[Any, Any, Any]] = _clients,
    fetch: Callable[..., Stats] = fetch_stats,
    out: Callable[[str], None] = print,
) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="affiche sans publier")
    parser.add_argument("--region", default="ca-central-1")
    parser.add_argument("--log-group", default="aws/spans")
    parser.add_argument("--topic-name", default="ask-my-cv-alerts")
    parser.add_argument(
        "--retention-days", type=int, default=14, help="rétention de aws/spans (jours)"
    )
    parser.add_argument("--now", type=float, default=None, help="horodatage UNIX (tests)")
    args = parser.parse_args(argv)

    logs, sns, sts = clients(args.region)
    now = args.now if args.now is not None else time.time()
    # une heure de marge : la rétention est appliquée en continu
    not_before = int(now) - args.retention_days * 86400 + 3600
    week, previous_week = last_full_weeks(now)
    current = fetch(logs, args.log_group, week, not_before=not_before)
    try:
        previous: Stats | None = fetch(logs, args.log_group, previous_week, not_before=not_before)
    except Exception as exc:  # groupe créé après cette semaine, ou plage refusée
        out(f"semaine précédente illisible ({type(exc).__name__}) : pas de comparaison")
        previous = None
    subject, message = format_summary(week, current, previous)

    if args.dry_run:
        out(f"[essai] objet : {subject}\n\n{message}")
        return 0
    # ARN construit sans jamais l'afficher (il contient le numéro de compte)
    account = sts.get_caller_identity()["Account"]
    topic_arn = f"arn:aws:sns:{args.region}:{account}:{args.topic_name}"
    sns.publish(TopicArn=topic_arn, Subject=subject, Message=message)
    out(f"résumé publié sur le sujet {args.topic_name} : {subject}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
