"""Consulter le journal des échanges publics (#150), en lecture seule.

python infra/scripts/exchanges.py [--days 7 | --date AAAA-MM-JJ] [--visitor HASH] [--json]
    [--region ca-central-1] [--table ask-my-cv-exchanges]

Utilise la session AWS du propriétaire (profil ou variables d'environnement) : une requête
`Query` par jour sur la table, rien d'autre. Affiche une transcription en français groupée par
visiteur (pseudonyme hebdomadaire `xops.visitor`) puis par heure : question, réponse affichée,
issue, langue. Le texte est déjà masqué à l'écriture (courriels, téléphones, URL, secrets).
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections.abc import Callable, Iterable, Sequence
from datetime import UTC, date, datetime, timedelta
from typing import Any

RESULTS = {
    "answered": "répondu",
    "refused": "refus (hors CV)",
    "withdrawn": "réponse retirée",
    "blocked": "bloqué",
    "rate_limited": "quota atteint",
    "budget_exceeded": "budget atteint",
    "error": "erreur",
    "cancelled": "interrompu",
}
LANGUAGES = {"fr": "français", "en": "anglais"}


def days_back(today: date, days: int) -> list[str]:
    """Jours UTC, du plus récent au plus ancien."""
    return [(today - timedelta(days=i)).isoformat() for i in range(days)]


def _value(attr: dict[str, Any]) -> Any:
    if "S" in attr:
        return attr["S"]
    if "N" in attr:
        return float(attr["N"])
    if "L" in attr:
        return [_value(v) for v in attr["L"]]
    return None


def parse_item(item: dict[str, Any]) -> dict[str, Any]:
    row = {k: _value(v) for k, v in item.items()}
    stamp, _, trace = str(row.get("sk", "")).partition("#")
    row["time"] = stamp
    row["trace_id"] = trace
    return row


def query_days(
    client: Any, table: str, day_list: Iterable[str], visitor: str | None = None
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for day in day_list:
        kwargs: dict[str, Any] = {
            "TableName": table,
            "KeyConditionExpression": "pk = :d",
            "ExpressionAttributeValues": {":d": {"S": day}},
        }
        if visitor:
            kwargs["FilterExpression"] = "visitor = :v"
            kwargs["ExpressionAttributeValues"][":v"] = {"S": visitor}
        while True:
            page = client.query(**kwargs)
            rows.extend(parse_item(i) for i in page.get("Items", []))
            if "LastEvaluatedKey" not in page:
                break
            kwargs["ExclusiveStartKey"] = page["LastEvaluatedKey"]
    return sorted(rows, key=lambda r: r["time"])


def _indent(text: str) -> str:
    return "\n".join(f"      {line}" for line in (text or "(vide)").splitlines() or ["(vide)"])


def format_transcript(rows: Sequence[dict[str, Any]]) -> str:
    if not rows:
        return "Aucun échange public sur la période.\n"
    groups: dict[str, list[dict[str, Any]]] = {}
    for row in rows:  # déjà triés par heure : l'ordre des visiteurs suit leur premier échange
        groups.setdefault(str(row.get("visitor") or "inconnu"), []).append(row)
    out = [f"{len(rows)} échange(s), {len(groups)} visiteur(s) (heures en UTC)."]
    for visitor, items in groups.items():
        out += ["", f"=== Visiteur {visitor} ({len(items)} échange(s)) ==="]
        for row in items:
            result = RESULTS.get(str(row.get("result")), str(row.get("result")))
            if reason := row.get("block_reason"):
                result += f" : {reason}"
            language = LANGUAGES.get(str(row.get("language")), row.get("language") or "?")
            kind = "annonce" if row.get("kind") == "ad" else "question"
            out += [
                "",
                f"[{str(row['time']).replace('T', ' ')[:19]}] {kind}, {language}, {result}",
                "  Question :",
                _indent(str(row.get("question", ""))),
                "  Réponse :",
                _indent(str(row.get("answer", ""))),
            ]
            if row.get("sources"):
                out.append(f"  Sources : {', '.join(row['sources'])}")
    return "\n".join(out) + "\n"


def _client(region: str) -> Any:
    import boto3

    return boto3.client("dynamodb", region_name=region)


def main(
    argv: Sequence[str] | None = None,
    *,
    client: Callable[[str], Any] = _client,
    out: Callable[[str], None] = print,
    now: Callable[[], float] = time.time,
) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=int, default=7, help="jours UTC à lire (défaut : 7)")
    parser.add_argument("--date", type=date.fromisoformat, help="un seul jour AAAA-MM-JJ")
    parser.add_argument("--visitor", help="pseudonyme hebdomadaire du visiteur")
    parser.add_argument("--json", action="store_true", help="sortie JSON brute")
    parser.add_argument("--region", default="ca-central-1")
    parser.add_argument("--table", default="ask-my-cv-exchanges")
    args = parser.parse_args(argv)
    if args.days < 1 or args.days > 31:
        parser.error("--days doit être compris entre 1 et 31 (rétention : 30 jours)")

    if args.date:
        day_list = [args.date.isoformat()]
    else:
        day_list = days_back(datetime.fromtimestamp(now(), UTC).date(), args.days)
    rows = query_days(client(args.region), args.table, day_list, args.visitor)
    if args.json:
        out(json.dumps(rows, ensure_ascii=False, indent=2))
    else:
        out(format_transcript(rows))
    return 0


if __name__ == "__main__":
    sys.exit(main())
