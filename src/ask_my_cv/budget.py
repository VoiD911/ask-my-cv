from __future__ import annotations

import time
from collections import defaultdict
from typing import Protocol


class RateLimited(Exception):
    """Le visiteur a posé trop de questions dans la fenêtre."""


class BudgetExceeded(Exception):
    """Le plafond de dépense du jour est atteint."""


class BudgetLedger(Protocol):
    def check(self, visitor: str, now: float) -> None: ...

    def record(self, provider_id: str, cost_usd: float, now: float) -> None: ...

    def spent_today(self, now: float) -> float: ...


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

    def check(self, visitor: str, now: float) -> None:
        if self.spent_today(now) >= self.daily_cap_usd:
            raise BudgetExceeded
        recent = [t for t in self._hits.get(visitor, []) if now - t < self.window_s]
        if len(recent) >= self.per_visitor_limit:
            self._hits[visitor] = recent
            raise RateLimited
        recent.append(now)
        self._hits[visitor] = recent

    def record(self, provider_id: str, cost_usd: float, now: float) -> None:
        self._spend[_day(now)][provider_id] += cost_usd

    def spent_today(self, now: float) -> float:
        return sum(self._spend.get(_day(now), {}).values())

    def spent_by_provider(self, now: float) -> dict[str, float]:
        return dict(self._spend.get(_day(now), {}))
