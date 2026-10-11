"""Purge quotidienne des traces Langfuse (#154) : python infra/scripts/langfuse_purge.py [--apply]

Les échanges publics sont annoncés conservés 30 jours. Sur l'offre Hobby, la rétention de
Langfuse n'est pas configurable : ce script supprime lui-même chaque trace (et, côté Langfuse,
ses observations et scores) dont l'observation racine a commencé avant le seuil.

Le seuil par défaut est de 28 jours, pas 30 : sur Hobby, l'API Observations v2 ne voit que les
30 derniers jours. Une trace plus ancienne ne serait plus trouvable, donc plus supprimable.
Deux jours de marge absorbent un ou deux échecs du job quotidien.

Essai par défaut : affiche seulement des nombres, jamais d'identifiant ni de contenu.
`--apply` supprime, par lots (`DELETE /api/public/traces`, `traceIds`). Suppression
asynchrone côté Langfuse (environ 15 minutes). Limites Hobby : 30 requêtes/min en lecture,
50 requêtes de suppression par jour et par organisation, d'où le plafond de lots par passage.
429 : attente selon `Retry-After` ; 5xx et erreurs réseau : nouvel essai avec attente
croissante. Tout échec, ou un reliquat non supprimé, sort en code non nul (alerte du job).

Clés du projet : LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY ; hôte : LANGFUSE_BASE_URL
(défaut https://us.cloud.langfuse.com).
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any, TextIO
from urllib.parse import urlparse

import requests

DEFAULT_BASE_URL = "https://us.cloud.langfuse.com"
DEFAULT_DAYS = 28
# fenêtre de lecture de l'API Observations v2 sur Hobby : au-delà, plus rien n'est trouvable
READ_WINDOW_DAYS = 30
PAGE_LIMIT = 1000
DELETE_BATCH = 1000
# 50 suppressions/jour/organisation sur Hobby : marge pour une relance manuelle
MAX_DELETE_REQUESTS = 40
MAX_PAGES = 500
MAX_ATTEMPTS = 5
TIMEOUT_S = 30.0
MAX_WAIT_S = 120.0


class PurgeError(Exception):
    """Échec de la purge : le message ne contient jamais de corps de réponse."""


class LangfuseClient:
    def __init__(
        self,
        base_url: str,
        public_key: str,
        secret_key: str,
        session: Any = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        parsed = urlparse(base_url)
        if parsed.scheme != "https" or not parsed.netloc:
            raise PurgeError("LANGFUSE_BASE_URL doit être une URL https")
        self.base_url = base_url.rstrip("/")
        self._auth = (public_key, secret_key)
        self._session = session if session is not None else requests.Session()
        self._sleep = sleep

    def request(
        self,
        method: str,
        path: str,
        params: dict[str, str] | None = None,
        body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                response = self._session.request(
                    method,
                    f"{self.base_url}{path}",
                    params=params,
                    json=body,
                    auth=self._auth,
                    timeout=TIMEOUT_S,
                )
            except requests.RequestException as exc:
                status, wait = type(exc).__name__, float(2**attempt)
            else:
                if 200 <= response.status_code < 300:
                    return response.json() if response.content else {}
                status = f"HTTP {response.status_code}"
                if response.status_code == 429:
                    wait = _retry_after(response.headers.get("Retry-After"), attempt)
                elif response.status_code >= 500:
                    wait = float(2**attempt)
                else:
                    # 400/401/403/404 : inutile de réessayer
                    raise PurgeError(f"{method} {path} : {status}")
            if attempt == MAX_ATTEMPTS:
                raise PurgeError(f"{method} {path} : {status} après {MAX_ATTEMPTS} essais")
            self._sleep(min(wait, MAX_WAIT_S))
        raise AssertionError("inatteignable")


def _retry_after(value: str | None, attempt: int) -> float:
    try:
        return max(0.0, float(value)) if value is not None else float(2**attempt)
    except ValueError:
        return float(2**attempt)


def _iso(moment: datetime) -> str:
    return moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def old_trace_ids(client: LangfuseClient, cutoff: datetime, now: datetime) -> list[str]:
    """Identifiants des traces dont l'observation racine a commencé avant `cutoff`.

    Début de la fenêtre explicite, une heure en deçà de la fenêtre de lecture Hobby, pour ne
    jamais demander une période que l'offre refuserait."""
    ids: dict[str, None] = {}
    params = {
        "fields": "core",
        "isRootObservation": "true",
        "fromStartTime": _iso(now - timedelta(days=READ_WINDOW_DAYS) + timedelta(hours=1)),
        "toStartTime": _iso(cutoff),
        "limit": str(PAGE_LIMIT),
    }
    for _ in range(MAX_PAGES):
        page = client.request("GET", "/api/public/v2/observations", params=params)
        for observation in page.get("data") or []:
            trace_id = observation.get("traceId")
            if isinstance(trace_id, str) and trace_id:
                ids[trace_id] = None
        cursor = (page.get("meta") or {}).get("cursor")
        if not cursor:
            return list(ids)
        params = {**params, "cursor": cursor}
    raise PurgeError(f"pagination interrompue après {MAX_PAGES} pages")


def purge(
    client: LangfuseClient, days: int, apply: bool, now: datetime, out: TextIO = sys.stdout
) -> int:
    cutoff = now - timedelta(days=days)
    ids = old_trace_ids(client, cutoff, now)
    print(f"seuil : {_iso(cutoff)} ({days} jours) ; traces à supprimer : {len(ids)}", file=out)
    if not apply:
        print("essai : rien n'est supprimé (--apply pour supprimer)", file=out)
        return 0
    batches = [ids[i : i + DELETE_BATCH] for i in range(0, len(ids), DELETE_BATCH)]
    for batch in batches[:MAX_DELETE_REQUESTS]:
        client.request("DELETE", "/api/public/traces", body={"traceIds": batch})
    deleted = sum(len(b) for b in batches[:MAX_DELETE_REQUESTS])
    print(f"suppression demandée : {deleted} traces (asynchrone côté Langfuse)", file=out)
    remaining = len(ids) - deleted
    if remaining:
        print(f"reliquat : {remaining} traces, au-delà de la limite quotidienne", file=out)
        return 2
    return 0


def main(argv: list[str] | None = None, session: Any = None) -> int:
    parser = argparse.ArgumentParser(description="Purge des traces Langfuse anciennes (#154)")
    parser.add_argument("--days", type=int, default=DEFAULT_DAYS)
    parser.add_argument("--apply", action="store_true", help="supprimer (essai sinon)")
    args = parser.parse_args(argv)
    if not 1 <= args.days < READ_WINDOW_DAYS:
        parser.error(f"--days doit être entre 1 et {READ_WINDOW_DAYS - 1}")
    public, secret = os.environ.get("LANGFUSE_PUBLIC_KEY"), os.environ.get("LANGFUSE_SECRET_KEY")
    if not public or not secret:
        print("ÉCHEC : LANGFUSE_PUBLIC_KEY et LANGFUSE_SECRET_KEY sont requis", file=sys.stderr)
        return 1
    try:
        client = LangfuseClient(
            os.environ.get("LANGFUSE_BASE_URL") or DEFAULT_BASE_URL, public, secret, session
        )
        return purge(client, args.days, args.apply, datetime.now(UTC))
    except PurgeError as exc:
        print(f"ÉCHEC : {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
