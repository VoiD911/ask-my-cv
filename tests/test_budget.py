import pytest

from ask_my_cv.budget import BudgetExceeded, InMemoryLedger, RateLimited

DAY = 86_400.0
T0 = 1_790_000_000.0


def test_rate_limit_per_visitor_within_window() -> None:
    ledger = InMemoryLedger(daily_cap_usd=10.0, per_visitor_limit=2, window_s=60)
    ledger.check("v1", T0)
    ledger.check("v1", T0 + 1)
    with pytest.raises(RateLimited):
        ledger.check("v1", T0 + 2)
    ledger.check("v2", T0 + 2)
    ledger.check("v1", T0 + 61)


def test_daily_cap_blocks_then_resets_next_day() -> None:
    ledger = InMemoryLedger(daily_cap_usd=0.01, per_visitor_limit=100, window_s=60)
    ledger.record("bedrock:haiku", 0.006, T0)
    ledger.check("v1", T0)
    ledger.record("bedrock:haiku", 0.006, T0)
    assert ledger.spent_today(T0) == pytest.approx(0.012)
    with pytest.raises(BudgetExceeded):
        ledger.check("v1", T0)
    ledger.check("v1", T0 + DAY)


def test_spend_is_tracked_per_provider() -> None:
    ledger = InMemoryLedger(daily_cap_usd=1.0, per_visitor_limit=10, window_s=60)
    ledger.record("a", 0.1, T0)
    ledger.record("b", 0.2, T0)
    assert ledger.spent_by_provider(T0) == {"a": pytest.approx(0.1), "b": pytest.approx(0.2)}


def test_in_memory_ledger_is_thread_safe() -> None:
    import sys
    from concurrent.futures import ThreadPoolExecutor

    ledger = InMemoryLedger(daily_cap_usd=1000.0, per_visitor_limit=50, window_s=3600)

    def attempt(_: int) -> bool:
        try:
            ledger.check("v", 0.0)
        except RateLimited:
            return False
        return True

    old_interval = sys.getswitchinterval()
    sys.setswitchinterval(1e-6)
    try:
        with ThreadPoolExecutor(max_workers=16) as pool:
            results = list(pool.map(attempt, range(500)))
    finally:
        sys.setswitchinterval(old_interval)

    assert sum(results) == 50
    assert len(results) - sum(results) == 450

    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(lambda _: ledger.record("p", 0.001, 0.0), range(2000)))
    assert abs(ledger.spent_by_provider(0.0)["p"] - 2.0) < 1e-9
