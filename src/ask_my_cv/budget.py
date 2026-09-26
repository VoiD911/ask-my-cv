from __future__ import annotations

import threading
import time
from collections import defaultdict
from typing import Protocol


class RateLimited(Exception):
    """Le visiteur a posé trop de questions dans la fenêtre."""


class BudgetExceeded(Exception):
    """Le plafond de dépense du jour est atteint."""


class BudgetLedger(Protocol):
    def check(self, visitor: str, now: float, limit: int | None = None) -> float:
        """Contrôle plafond et quota, compte la question ; renvoie la dépense du jour.

        `limit` remplace la limite par visiteur (compartiment d'évaluation) ; le plafond de
        dépense s'applique toujours.
        """
        ...

    def record(self, provider_id: str, cost_usd: float, now: float) -> None: ...

    def spent_today(self, now: float) -> float: ...

    def spent_by_provider(self, now: float) -> dict[str, float]: ...


def _day(now: float) -> str:
    return time.strftime("%Y-%m-%d", time.gmtime(now))


class InMemoryLedger:
    """Quotas et dépenses en mémoire (un seul processus) ; DynamoDB en 1c."""

    def __init__(self, daily_cap_usd: float, per_visitor_limit: int, window_s: float) -> None:
        self.daily_cap_usd = daily_cap_usd
        self.per_visitor_limit = per_visitor_limit
        self.window_s = window_s
        self._hits: dict[str, list[float]] = {}
        self._spend: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
        self._lock = threading.Lock()

    def check(self, visitor: str, now: float, limit: int | None = None) -> float:
        limit = self.per_visitor_limit if limit is None else limit
        with self._lock:
            spent = self._spent(now)
            if spent >= self.daily_cap_usd:
                raise BudgetExceeded
            recent = [t for t in self._hits.get(visitor, []) if now - t < self.window_s]
            if len(recent) >= limit:
                self._hits[visitor] = recent
                raise RateLimited
            recent.append(now)
            self._hits[visitor] = recent
            return spent

    def record(self, provider_id: str, cost_usd: float, now: float) -> None:
        with self._lock:
            self._spend[_day(now)][provider_id] += cost_usd

    def spent_today(self, now: float) -> float:
        with self._lock:
            return self._spent(now)

    def spent_by_provider(self, now: float) -> dict[str, float]:
        with self._lock:
            return dict(self._spend.get(_day(now), {}))

    def _spent(self, now: float) -> float:
        """Calcul sans verrou : appelé par `check` (déjà sous verrou) et `spent_today`."""
        return sum(self._spend.get(_day(now), {}).values())
