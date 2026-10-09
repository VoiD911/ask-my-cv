import importlib.util
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

_SCRIPT_PATH = Path(__file__).resolve().parents[1] / "infra" / "scripts" / "weekly_summary.py"
spec = importlib.util.spec_from_file_location("weekly_summary", _SCRIPT_PATH)
assert spec and spec.loader
weekly = importlib.util.module_from_spec(spec)
sys.modules["weekly_summary"] = weekly  # requis par @dataclass
spec.loader.exec_module(weekly)

# mercredi 2026-09-30 15:00 UTC : semaine rapportée = lundi 21 au dimanche 27 septembre
NOW = datetime(2026, 9, 30, 15, tzinfo=UTC).timestamp()


def fake_results(**totals: str) -> dict[str, list[dict[str, str]]]:
    return {
        "totals": [
            {
                "requests": "42",
                "questions": "30",
                "ads": "12",
                "attacks": "5",
                "refusals": "3",
                "withdrawn": "1",
                "spent": "0.1234",
                **totals,
            }
        ],
        "visitors": [{"visitors": "17"}],
        "languages": [{"language": "fr", "n": "30"}, {"language": "en", "n": "10"}],
        "all_cost": [{"cost": "0.4"}],
        "internal": [{"requests": "20", "spent": "0.2"}],
    }


def test_last_full_weeks_are_iso_weeks_in_utc() -> None:
    current, previous = weekly.last_full_weeks(NOW)
    assert (current.start, current.end) == (
        datetime(2026, 9, 21, tzinfo=UTC),
        datetime(2026, 9, 28, tzinfo=UTC),
    )
    assert previous.end == current.start
    assert current.label == "du 2026-09-21 au 2026-09-27"
    # un lundi : la semaine rapportée est celle qui vient de finir
    monday = datetime(2026, 9, 28, 12, tzinfo=UTC).timestamp()
    assert weekly.last_full_weeks(monday)[0] == current


def test_to_stats_reads_logs_insights_rows() -> None:
    stats = weekly.to_stats(fake_results())
    assert (stats.visitors, stats.requests, stats.questions, stats.ads) == (17, 42, 30, 12)
    assert (stats.attacks, stats.refusals, stats.withdrawn) == (5, 3, 1)
    assert stats.cost_usd == pytest.approx(0.1234)
    assert stats.all_cost_usd == pytest.approx(0.4)
    assert (stats.top_language, stats.top_language_share) == ("fr", 0.75)


def test_to_stats_of_an_empty_week_is_all_zero() -> None:
    stats = weekly.to_stats(
        {"totals": [], "visitors": [], "languages": [], "all_cost": [], "internal": []}
    )
    assert stats == weekly.Stats()


def test_summary_is_french_compares_weeks_and_has_an_ascii_subject() -> None:
    week, _ = weekly.last_full_weeks(NOW)
    current = weekly.to_stats(fake_results())
    previous = weekly.to_stats(fake_results(requests="21", attacks="0", spent="0.1234"))
    subject, message = weekly.format_summary(week, current, previous)
    assert subject.isascii() and "\n" not in subject and len(subject) <= 100
    assert "semaine du 2026-09-21 au 2026-09-27" in message
    assert "- Visiteurs distincts : 17 (semaine précédente : 17, stable)" in message
    assert "- Requêtes : 42 (semaine précédente : 21, +100 %)" in message
    assert "- Attaques bloquées : 5 (semaine précédente : 0, nouveau)" in message
    assert "- Annonces collées : 12" in message
    assert "- Réponses retirées par le garde de sortie : 1" in message
    assert "- Coût du trafic public : 0,12 USD (semaine précédente : 0,12 USD, stable)" in message
    assert "0,40 USD" in message
    assert "Langue principale : français (75 %)" in message
    assert "Trafic interne exclu" in message


def test_summary_of_a_quiet_week_says_so() -> None:
    week, _ = weekly.last_full_weeks(NOW)
    _, message = weekly.format_summary(week, weekly.Stats(), weekly.Stats())
    assert "Aucune requête publique cette semaine." in message
    assert "Langue principale : aucune donnée" in message


class FakeLogs:
    def __init__(self, statuses: list[str], rows: list[Any] | None = None) -> None:
        self.statuses = statuses
        self.rows = rows or []
        self.started: list[dict[str, Any]] = []

    def start_query(self, **kwargs: Any) -> dict[str, str]:
        self.started.append(kwargs)
        return {"queryId": "q-1"}

    def get_query_results(self, queryId: str) -> dict[str, Any]:  # noqa: N803 (API boto3)
        status = self.statuses.pop(0)
        return {"status": status, "results": self.rows if status == "Complete" else []}


def test_run_query_polls_until_complete_within_the_week() -> None:
    week, _ = weekly.last_full_weeks(NOW)
    logs = FakeLogs(["Running", "Complete"], [[{"field": "requests", "value": "3"}]])
    rows = weekly.run_query(logs, "aws/spans", "q", week, sleep=lambda _: None)
    assert rows == [{"requests": "3"}]
    [call] = logs.started
    assert call["startTime"] == int(week.start.timestamp())
    assert call["endTime"] == int(week.end.timestamp()) - 1


@pytest.mark.parametrize("statuses", [["Failed"], ["Running"] * 3])
def test_run_query_fails_loudly(statuses: list[str]) -> None:
    week, _ = weekly.last_full_weeks(NOW)
    with pytest.raises(weekly.SummaryError):
        weekly.run_query(
            FakeLogs(statuses), "aws/spans", "q", week, max_polls=3, sleep=lambda _: None
        )


def test_every_query_filters_on_the_root_span_and_never_reads_text() -> None:
    for name, query in weekly.QUERIES.items():
        assert query.startswith('filter name = "ask"'), name
        if name not in {"all_cost", "internal"}:
            assert '`attributes.xops.traffic` = "public"' in query, name
        assert "observation.input" not in query, name
        assert "@message" not in query, name


class FakeSns:
    def __init__(self) -> None:
        self.published: list[dict[str, str]] = []

    def publish(self, **kwargs: str) -> None:
        self.published.append(kwargs)


class FakeDynamo:
    def __init__(self, by_day: dict[str, list[dict[str, Any]]], fail: bool = False) -> None:
        self.by_day = by_day
        self.fail = fail
        self.calls: list[dict[str, Any]] = []

    def query(self, **kwargs: Any) -> dict[str, Any]:
        if self.fail:
            raise RuntimeError("ResourceNotFoundException")
        self.calls.append(kwargs)
        items = self.by_day.get(kwargs["ExpressionAttributeValues"][":d"]["S"], [])
        return {"Items": items[: kwargs["Limit"]]}


def exchange_item(day: str, hour: int, question: str, answer: str) -> dict[str, Any]:
    return {
        "pk": {"S": day},
        "sk": {"S": f"{day}T{hour:02d}:00:00.000Z#t{hour}"},
        "question": {"S": question},
        "answer": {"S": answer},
        "result": {"S": "answered"},
        "language": {"S": "fr"},
        "visitor": {"S": "abc"},
        "sources": {"L": [{"S": "[1] X"}]},
    }


# plus récent d'abord (ScanIndexForward=False) ; NOW = mercredi 2026-09-30
EXCHANGES = {
    "2026-09-30": [exchange_item("2026-09-30", h, f"Question {h}", "Réponse") for h in (14, 9)],
    "2026-09-28": [
        exchange_item("2026-09-28", h, "Q " + "x" * 500, "R " + "y" * 500)
        for h in range(20, 10, -1)
    ],
}


class FakeSts:
    def get_caller_identity(self) -> dict[str, str]:
        return {"Account": "000000000000"}


def run_main(argv: list[str]) -> tuple[FakeSns, list[str], list[Any]]:
    sns, printed, fetched = FakeSns(), [], []

    def fetch(_logs: Any, log_group: str, week: Any, not_before: int = 0) -> Any:
        fetched.append(week)
        return weekly.to_stats(fake_results())

    code = weekly.main(
        [*argv, "--now", str(NOW)],
        clients=lambda _region: (object(), sns, FakeSts()),
        fetch=fetch,
        out=printed.append,
        dynamodb=lambda _r: FakeDynamo(EXCHANGES),
    )
    assert code == 0
    return sns, printed, fetched


def test_dry_run_prints_and_never_publishes() -> None:
    sns, printed, fetched = run_main(["--dry-run"])
    assert sns.published == []
    assert len(fetched) == 2 and fetched[0].start > fetched[1].start
    [text] = printed
    assert text.startswith("[essai] objet : ask-my-cv : resume hebdomadaire (2026-09-21)")
    assert "Requêtes : 42" in text


def test_real_run_publishes_once_to_the_alerts_topic_without_printing_the_arn() -> None:
    sns, printed, _ = run_main([])
    [published] = sns.published
    assert published["TopicArn"] == "arn:aws:sns:ca-central-1:000000000000:ask-my-cv-alerts"
    assert published["Subject"].isascii()
    assert "Visiteurs distincts : 17" in published["Message"]
    assert not any("000000000000" in line for line in printed)


def test_previous_week_unreadable_means_no_comparison() -> None:
    week, _ = weekly.last_full_weeks(NOW)
    _, message = weekly.format_summary(week, weekly.to_stats(fake_results()), None)
    assert "- Requêtes : 42 (semaine précédente : indisponible)" in message
    assert "- Coût du trafic public : 0,12 USD (semaine précédente : indisponible)" in message


def test_main_survives_an_unreadable_previous_week() -> None:
    printed: list[str] = []
    calls: list[int] = []

    def fetch(_logs: Any, _group: str, week: Any, not_before: int = 0) -> Any:
        calls.append(not_before)
        if len(calls) == 2:
            raise RuntimeError("MalformedQueryException")
        return weekly.to_stats(fake_results())

    code = weekly.main(
        ["--dry-run", "--now", str(NOW)],
        clients=lambda _r: (object(), FakeSns(), FakeSts()),
        fetch=fetch,
        out=printed.append,
        dynamodb=lambda _r: FakeDynamo({}),
    )
    assert code == 0
    assert calls[0] == int(NOW) - 14 * 86400 + 3600
    assert "semaine précédente : indisponible" in printed[-1]


def test_run_query_clamps_to_retention_and_skips_expired_weeks() -> None:
    week, previous = weekly.last_full_weeks(NOW)
    logs = FakeLogs(["Complete"])
    floor = int(week.start.timestamp()) + 3600
    weekly.run_query(logs, "aws/spans", "q", week, sleep=lambda _: None, not_before=floor)
    assert logs.started[0]["startTime"] == floor
    expired = FakeLogs([])
    assert weekly.run_query(expired, "g", "q", previous, not_before=floor) == []
    assert expired.started == []


def test_stats_only_aggregate_fields_defined_by_the_query() -> None:
    import re

    for name, query in weekly.QUERIES.items():
        defined = set(re.findall(r" as (\w+)", query))
        stats = query[query.index("| stats") :]
        used = set(re.findall(r"(?:sum|pct)\((\w+)", stats))
        assert used <= defined, (name, used - defined)


@pytest.mark.parametrize(
    ("internal", "flagged"),
    [
        ({"requests": "20", "spent": "0.2"}, False),
        ({"requests": "60", "spent": "0.1"}, True),  # > public (42) et > 50
        ({"requests": "45", "spent": "0.1"}, False),  # > public mais sous le plancher de 50
        ({"requests": "5", "spent": "0.3"}, True),  # coût > 2 × public (0,1234)
    ],
)
def test_abnormal_internal_traffic_is_flagged(internal: dict, flagged: bool) -> None:
    week, _ = weekly.last_full_weeks(NOW)
    stats = weekly.to_stats({**fake_results(), "internal": [internal]})
    _, message = weekly.format_summary(week, stats, stats)
    assert ("À VÉRIFIER : trafic interne anormal" in message) is flagged
    assert f"- Trafic interne : {internal['requests']} requêtes" in message


def test_recent_exchanges_newest_first_capped_at_ten() -> None:
    fake = FakeDynamo(EXCHANGES)
    rows = weekly.fetch_recent_exchanges(fake, "t", NOW)
    assert len(rows) == 10
    assert rows[0]["question"] == "Question 14"
    assert all(c["ScanIndexForward"] is False for c in fake.calls)
    assert [c["Limit"] for c in fake.calls] == [10, 8, 8]  # 30, 29 (vide), 28


def test_exchanges_section_is_masked_and_truncated() -> None:
    rows = [
        {
            "sk": "2026-09-30T14:00:00.000Z#t",
            "question": "Écris à a.b@acme.fr " + "x" * 500,
            "answer": "Appelle le 06 12 34 56 78 " + "y" * 500,
            "result": "answered",
            "language": "fr",
            "visitor": "abc",
        }
    ]
    lines = weekly.format_exchanges(rows)
    text = "\n".join(lines)
    assert "[2026-09-30 14:00] answered, fr, visiteur abc" in text
    assert "a.b@acme.fr" not in text and "[e-mail]" in text
    assert "06 12 34 56 78" not in text
    question = next(line for line in lines if line.startswith("  Q : "))
    answer = next(line for line in lines if line.startswith("  R : "))
    assert len(question) == len("  Q : ") + weekly.QUESTION_PREVIEW
    assert len(answer) == len("  R : ") + weekly.ANSWER_PREVIEW


def test_real_run_includes_the_exchanges_but_dry_run_only_counts_them() -> None:
    sns, _, _ = run_main([])
    message = sns.published[0]["Message"]
    assert "Derniers échanges (10, du plus récent, heures UTC) :" in message
    assert "Question 14" in message
    _, printed, _ = run_main(["--dry-run"])
    assert "Derniers échanges : 10 (texte omis en essai)." in printed[-1]
    assert "Question 14" not in printed[-1]


def test_unreadable_exchange_table_does_not_block_the_summary() -> None:
    sns, printed = FakeSns(), []
    code = weekly.main(
        ["--now", str(NOW)],
        clients=lambda _r: (object(), sns, FakeSts()),
        fetch=lambda *_a, **_k: weekly.to_stats(fake_results()),
        out=printed.append,
        dynamodb=lambda _r: FakeDynamo({}, fail=True),
    )
    assert code == 0
    assert "Derniers échanges : indisponibles (RuntimeError)." in sns.published[0]["Message"]
